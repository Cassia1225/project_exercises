# MQTT・API・市区町村指定の結合 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 任意アレルギー・市区町村・日付を指定し、実際のMQTTとHTTPを経由して結果を表示するアプリを、本人が起動できる状態にする。

**Architecture:** 既存設計の5プログラム（Streamlit、Controller、気象、花粉、推薦）とローカルBrokerを採る。Controllerと推薦はPython標準HTTPサーバー、気象・花粉はMQTT要求/返信。ブラウザー位置→国内市区町村の特定→自治体の代表座標→両API取得とする。

**Tech Stack:** Python、requests、paho-mqtt、aMQTT（ローカル開発Broker）、Streamlit、pytest、ブラウザーGeolocation/localStorage。

**Spec:** `docs/pollen-navi-app-design-v0.2-2026-10-18.md`。追加指示：現在地は現在いる市区町村のデータを取得する。

## Global Constraints

- 既存Testブランチと第1段階の変更を継続。コミット・push・実DB変更は行わない。
- 日本国内、ログイン・DB・結果履歴なし。保存対象は任意のアレルギー設定のみ。
- UPI0〜1低、2〜3中、4高、5非常に高い。風・設定一致による加算なし。
- 個人レベルは設定種の有効UPI最大。一部不足は暫定、全設定種不足は判定不可。TREEをスギへ代用しない。
- schema_version=1.2-draft、QoS1、retain=false、検索ID/日付/位置/送信元/期限の照合。個人設定はMQTTへ送信しない。
- 日付は今日〜明後日のISO日付。APIから別日を黙って流用しない。風速m/s、気象Asia/Tokyo・花粉UTCを明記。
- 外部APIキーは環境変数。キー不足や部分失敗を隠さない。デモ値はis_mock=trueで明示。
- サーバーと開発Brokerは127.0.0.1を初期値とする。Geminiは今回呼び出さず、対策生成差替えの境界を残す。
- 現在地が国内市区町村に解決できなければ手動検索を案内。位置の自動追跡・永続保存なし。

## Review Focus

1. 同時検索・重複/遅延返信で、別の利用者や日付の結果が混ざらない。
2. 真偽値UPI、UPI0、植物不足で、誤って個人レベルを確定しない。
3. 海外座標・曖昧な市名・位置取得拒否で、勝手に別地域を採用しない。
4. 保存設定の初回復元、削除、壊れた保存値で、空設定の自動上書きや検索の自動連打を起こさない。
5. Broker/担当停止・API失敗・ポート競合時に期限内に理由を返し、起動した子プロセスを終了できる。

### Task 1: 種類別推薦とJSON契約

**Files:** Create `common/protocol.py`, `recommend/service.py`, package initializers, `tests/test_assessment.py`.
**Interfaces:** Produces `assess(payload: dict)->dict`、`validate_query(payload:dict)->dict`、`validate_worker_request(payload:dict)->dict`、`matches_result(reply,request,source)->bool`。結果は設計書のdata/details/errors/warnings/metaを持つ。

- [x] まずテスト：UPI全境界、bool/欠測、選択種最大・一部/全不足、未設定、片方/両方API失敗、風によるレベル不変、返信ID/日付/位置不一致の拒否。
- [x] Run `env/bin/python -m pytest tests/test_assessment.py -q`。Expected: 未実装の失敗。
- [x] 上記の純粋関数を実装。ルール文は既存内容を参考にした実演用と明記し、将来の文生成を判定と分離する。
- [x] 同じテストを実行。Expected: PASS。

### Task 2: 位置解決・気象/花粉API

**Files:** Create `server/locations.py`, `common/providers.py`, `tests/test_providers.py`; Modify `weather/get_weather_data.py`, `pollen/get_pollen_data.py`.
**Interfaces:** `Locations.search(query)->list[dict]`, `Locations.current(lat,lon)->dict`, `Locations.resolve(candidate_id)->dict`。位置はlocation_id/name/latitude/longitude/municipality_code。`get_weather(request)->dict`, `get_pollen(request)->dict`は正規化dataを返し、失敗はキーを含まない例外。

- [x] まずテスト：国内市区町村候補、同名地域、東京駅座標→千代田区、海外/候補不正、選択日完全一致、m/s、dailyInfo、植物/分類分離、キー不足・HTTP異常・不正JSON。
- [x] Run `env/bin/python -m pytest tests/test_providers.py -q`。Expected: 未実装の失敗。
- [x] 国土地理院の検索・逆引きで自治体を特定し、自治体の代表点を使う。タイムアウト・空結果・HTTP失敗を明示。Open-MeteoとGoogle Pollenを正規化し、デモ用データは別関数にする。
- [x] 同じテストを実行。Expected: PASS。キー不要の実APIは既知の地域で別途確認し、実Google未確認を記録する。

### Task 3: MQTT要求/返信とHTTP集約

**Files:** Create `common/mqtt_transport.py`, `common/http_api.py`, `weather/worker.py`, `pollen/worker.py`, `recommend/api.py`, `server/api.py`, `server/controller.py`, `tests/test_transport.py`, `tests/test_http.py`; Modify 旧送受信入口。
**Interfaces:** `MqttCollector.collect(location,date,is_mock)->dict[source,reply]`、`Worker(source,provider).run()`。HTTP: GET `/health`, GET `/api/v1/locations?query=`, POST `/api/v1/locations/current`, POST `/api/v1/recommendations`, POST `/api/v1/evaluate`（推薦のみ）。

- [x] まずテスト：購読完了前に送らない、相関照合、重複、期限、担当停止、HTTP入力異常・推薦停止。外部APIはfixture、通信はローカルBrokerで追加確認。
- [x] Run `env/bin/python -m pytest tests/test_transport.py tests/test_http.py -q`。Expected: 未実装の失敗。
- [x] 期限付きCollector・再接続可能worker・独立HTTP入口を実装。並行API取得、共通検証、構造化エラー、設定のMQTT非送信を守る。
- [x] 同じテストを実行。Expected: PASS。

### Task 4: UI・ブラウザー設定・現在地

**Files:** Modify `UI/app.py`; Create `UI/browser_component/index.html`, `UI/browser.py`, `UI/state.py`, `tests/test_ui.py`.
**Interfaces:** UIはController HTTPのみを呼ぶ。ブラウザーcomponentは復元/保存/削除/現在地イベントをID付きで返し、再処理を防ぐ。設定以外をlocalStorageに保存しない。

- [x] まずテスト：保存値の検証、イベント重複、未設定、検索前のAPI非呼出し、partial表示、種類別結果、拒否時の手動検索。Streamlit AppTestでフォームと結果を確認。
- [x] Run `env/bin/python -m pytest tests/test_ui.py -q`。Expected: 未実装の失敗。
- [x] 復元完了後に入力し、明示ボタンで検索。候補選択・現在地から得た自治体表示・動的対策・出典/取得時刻/暫定を表示。デモを実取得と混ぜない。
- [x] 同じテストを実行。Expected: PASS。ブラウザーの位置権限・再訪問は実機確認と区別する。

### Task 5: 一括起動・手順・結合確認

**Files:** Create `run.py`, `common/broker.py`, `.env.example`, `requirements-dev.txt`, `tests/test_runtime.py`, `docs/implementation/2026-10-18-integration.md`; Modify `requirements.txt`, `README.md`, 設計書。
**Interfaces:** `python run.py --demo`で全プロセス起動、`python run.py`で実API。`--no-ui`で結合試験。Ctrl+C/子プロセス失敗時は今回起動した子を終了。

- [x] まずテスト：起動順、使用中ポート、子失敗/終了処理。Run `env/bin/python -m pytest tests/test_runtime.py -q`。Expected: 未実装の失敗。
- [x] 依存・設定例・起動処理を実装。READMEに新規環境作成、デモ実行、キー設定、実取得、停止、別PC化の入口を記す。
- [x] 全体Run `PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 env/bin/python -m pytest -q -p no:cacheprovider --ignore=env --ignore=test_supabase.py`。Expected: PASS。
- [x] 実Broker＋別プロセス＋HTTPを使うデモ結合、キー不要実API、市区町村解決、担当停止を確認。実Google花粉・本人GPS権限は未確認とする。
- [x] 全体を独立レビューし、重大な指摘は再現テストRED→GREENで修正。Notion設計書とAI_memoryへ結果を記録する。
