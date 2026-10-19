# 第1段階：花粉UPIと対策レベル Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. Execution method must be selected during review; native execution by 綾華 is recommended for this small change.

**Goal:** 現行の推薦処理について、数値花粉指数をUPI 0〜5で分類し、風やアレルギー設定一致でレベルが変わらない状態を作る。

**Architecture:** 既存の`normalize_pollen()`→`evaluate()`→`recommend()`の流れを保つ。最初は判定基礎だけを変え、旧入出力1.0のまま単体で確認する。次の段階で植物別データ・欠測・1.2-draftの契約へ移るため、第1段階の終了を最新プロトコル完成と呼ばない。

**Tech Stack:** Python 3、既存のpytest。外部通信・新規ライブラリ・DB変更なし。

**Spec:** `docs/pollen-navi-app-design-v0.2-2026-10-18.md`、特に6.1、6.2、14章。現状の根拠は`docs/implementation/2026-10-18-code-audit.md`。

## Global Constraints

- レベルはPythonが花粉指数から決め、風や設定一致で加算しない。
- UPI 0〜1は低、2〜3は中、4は高、5は非常に高い。
- 未取得を0として扱わず、bool、負数、6以上、非整数、NaN、無限値はUPIの有効値にしない。
- この段階では従来の入力文字列の正規化を維持する。整数を表す数値/数値文字列は正規化後に0〜5の範囲を検証する。新規の通信契約で要求する厳密なJSON型検証は第2段階に分ける。
- `SCHEMA_VERSION="1.0"`と現在の返却キーを今回は維持し、1.2-draft対応を装わない。
- `recommend/recommend.py`の本人の未コミットコメントを保持し、設計書の題名・作成者など本人の編集を上書きしない。
- 現行ブランチ`Test`を継続する案。新ブランチ/worktree作成、commit/push、実API、DB操作は今回の変更に含めない。
- 具体的な対策文と気象閾値は今回新たに決めず、既存の対策生成とAIアダプターを維持する。

## Review Focus

- 0/1/2/3/4/5の境界を一つずつ確認する（Task 1のパラメーター化試験）。
- bool・範囲外・小数・非有限値が有効UPIとして扱われない（Task 1の入力拒否試験）。
- UPI 0を欠測扱いしない（Task 1の0を含む分類と公開関数の試験）。
- 風と設定一致を変えても同じ花粉でレベルが変わらない（Task 2の組合せ試験）。
- 既存のAI対策文・失敗時フォールバック・文脈の個人情報除外が壊れない（Task 2の既存31件を更新して回帰確認）。

## Files

- Modify: `recommend/recommend.py`：UPI数値の検証と分類、`evaluate()`の加点削除。
- Modify: `recommend/test_recommend.py`：最新のレベル規則を検証する試験を追加し、旧加点に依存する期待値だけ更新する。
- Update after execution: 本計画の実施状況、コード確認記録、Notionの実装記録。

新しいモジュール構成やHTTP入口はこの段階では作らない。

## Task 1: 数値をUPIとして正しく分類する

**Interfaces:** Consumes `normalize_pollen(raw: Any) -> str`。Produces 同じ関数の`low/medium/high/very_high`と、既存`InputError`による不正入力通知。`recommend()`の外部引数は変更しない。

- [x] **Step 1: 次の分類試験を追加する。**

```python
@pytest.mark.parametrize(("upi", "category", "level"), [
    (0, "low", "低"), (1, "low", "低"),
    (2, "medium", "中"), (3, "medium", "中"),
    (4, "high", "高"), (5, "very_high", "非常に高い"),
])
def test_upi_boundaries(upi, category, level):
    from recommend import normalize_pollen
    assert normalize_pollen(upi) == category
    request = dict(SAMPLE, Pollen=upi, Wind=1, pollen_types=[])
    response = recommend(request)
    assert response["status"] == "success"
    assert response["data"]["level"] == level
```

- [x] **Step 2: `test_invalid_upi_is_rejected`を追加する。** `[-1, 6, 2.5, True, False, None, float("nan"), float("inf")]`をパラメーター化し、`normalize_pollen()`が`InputError`を送出、`recommend(dict(SAMPLE, Pollen=raw))`が`status="error"`、`data=None`を返すことを確認する。
- [x] **Step 3: 追加試験だけを実行して不合格を確認する。** `PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 env/bin/python -m pytest -q -p no:cacheprovider recommend/test_recommend.py -k 'upi_boundaries or invalid_upi'`。現状はUPI 2〜5および一部の不正値で失敗することが期待される。
- [x] **Step 4: 数値分類を修正する。** `_pollen_from_number(v: float) -> str`で有限・整数相当・0〜5を検証し、0〜1/2〜3/4/5の4区分へ変換する。`POLLEN_NUMERIC_SCALE`と個数20/50/80の分岐を外し、数値の尺度を一意にする。既存の日本語・英語の分類文字列は引き続き正規化する。
- [x] **Step 5: Step 3と同じ試験を再実行し、すべて合格することを確認する。**

## Task 2: 風・アレルギー一致によるレベル加算を外す

**Interfaces:** Consumes `evaluate(pollen_cat: str, wind_cat: str, weather_cat: str, matched_allergies: Optional[List[str]]) -> dict`。Produces 同じ`level/items/reasons`。レベルだけは常に花粉区分に対応し、対策・理由の既存処理は維持する。

- [x] **Step 1: `test_level_depends_only_on_pollen`を追加する。** 花粉区分4種類、風区分3種類、設定一致あり/なし、天気clear/rainを組み合わせ、`evaluate()`のlevelが`low→低、medium→中、high→高、very_high→非常に高い`となることを確認する。
- [x] **Step 2: `test_recommend_keeps_low_upi_low_in_strong_wind`を追加する。** `dict(SAMPLE, Pollen=1, Wind=9, pollen_types=["tree"], user={"allergies":["スギ"]})`に対し、`recommend()`のlevelが「低」であることを確認する。
- [x] **Step 3: Task 2の追加試験を実行して不合格を確認する。** `PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 env/bin/python -m pytest -q -p no:cacheprovider recommend/test_recommend.py -k 'level_depends_only_on_pollen or keeps_low_upi'`。
- [x] **Step 4: `evaluate()`の風・設定一致の`score += 1`を除く。** 対策・理由の変更は、この加点を除いたレベルに従うために必要な箇所に限る。文言、閾値、対策マスターの新規追加は行わない。
- [x] **Step 5: `test_minimal_context_does_not_include_location_or_user_id`の旧加点に基づく期待レベルを「非常に高い」から「高」へ更新する。** 個人情報がAI文脈に含まれないこと、設定種や基本対策が渡ることの確認は残す。他の失敗を単に期待値変更で通さない。
- [x] **Step 6: 全推薦テストを実行する。** `PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 env/bin/python -m pytest -q -p no:cacheprovider recommend/test_recommend.py`。追加試験と既存試験がすべて合格し、実API/DBを呼んでいないことを確認する。
- [x] **Step 7: 変更差分と作業状態を確認する。** `git diff --check`、`git diff -- recommend/recommend.py recommend/test_recommend.py`、`git status --short --branch`。本人のコメントが残り、今回対象外のアプリファイルが変更されていないことを確認する。
- [x] **Step 8: 結果を文書・Notionへ反映し、第1段階として報告する。** 試験の実数・結果、未実装の種類別判定/partial/1.2-draft/通信/UIを明記する。コミット・pushは行わない。

## 第1段階の完了条件と後続への引継ぎ

数値UPI 0〜5の分類が正しく、不正UPIを採用せず、風と設定一致がレベルを変えず、既存のAI関連の回帰確認を含め合格していること。第2段階では、植物別UPI・設定種の照合・一部欠測/全種未取得・気象欠測・`details/meta`を含む新しい入出力へ移行する。

第1段階終了時も、現在のUIのダミー経路、DB必須のController、固定Topic/座標、実API整形は未修正である。アプリ全体の完成とは報告しない。

## レビューと実行状況

- [x] 現行コード・本人の差分・設計書を確認。
- [x] 既存31件の合格と、新仕様の判定不一致を修正前コードで確認。
- [x] 第1段階を輸送方法に依存しない2タスクへ分割して計画。
- [x] 本人が本計画を確認し、綾華による順次実行またはサブエージェント方式を選ぶ。
- [x] 実装・検証。

計画作成時点ではアプリコード未変更。superpowersの実装計画スキルに従い、書面の計画レビュー後に実装へ進む。


## 実行結果（2026-10-18）

本人が計画を確認し、「綾華が順に実装する」を選択したため、承認された2タスクを実施した。

- Task 1：修正前の追加試験8件不合格→修正後、既存分を含め45件合格。
- Task 2：修正前の追加試験25件不合格→修正後、合計94件合格。
- 独立した最終レビューでも94件合格を確認。巨大整数の既存OverflowErrorが指摘されたため、通常の入力エラー辞書を返す契約に含めて修正した。正負の巨大整数2件を追加し、2件不合格→修正後合格を確認した。
- 最終のプロジェクト試験は96件合格。実行コマンドは`PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 env/bin/python -m pytest -q -p no:cacheprovider --ignore=env --ignore=test_supabase.py`。依存環境envと、対話式のAuth/DB書込みスクリプトtest_supabase.pyは除外した。
- `git diff --check`も問題なし。アプリの変更は推薦本体と推薦テストの2ファイル。本人の既存コメントを保持した。コミット・push・実API/実DB/実Broker接続はしていない。
- コミットしない計画に合わせ、最終レビューには未コミット差分の固定スナップショットを使用した。レビュー後のコード変更は上記の回帰試験を伴う1回の修正のみで、最後に差分のハッシュを再記録した。
- 第1段階の対象外は当初どおり後続へ引き継ぐ。既存の対策文/閾値/理由、float正規化による高精度数値文字列の丸めも維持したため、厳密な新JSON契約や対策文の最終確認は次段階で行う。
