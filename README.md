# 花粉対策ナビ

日本国内の市区町村・日付を指定し、日別の花粉・気象と対策を表示する授業用アプリです。アレルギー設定は任意で、同じブラウザーに保存します。ログイン、DB、結果履歴は使いません。

## 最初に動かす（デモ）

Python 3.14で確認しています。リポジトリのルートで実行してください。

```bash
python3 -m venv env
source env/bin/activate
python -m pip install -r requirements.txt
python run.py --demo
```

既に`env`がある場合は作り直さず、`source env/bin/activate`から始めます。Windowsの場合は有効化を`env\Scripts\activate`に読み替えます（Windows実機は未検証）。

起動完了が表示されたら、ブラウザーで **http://localhost:8501** を開きます。停止は起動した端末で **Ctrl+C**。今回起動したBroker・5担当をまとめて終了します。

1. アレルギーを任意で選びます。未設定でも検索できます。
2. 都道府県を選び、その中の市区町村を選びます。または「現在地から市区町村を選ぶ」を押します。
3. 対象日を選び、「花粉・気象と対策を取得」を押します。

**デモの気象・花粉は架空値です。** 通信は実際のMQTT・HTTPで行います。地域一覧の読み込み・現在地からの自治体特定にはインターネット接続が必要です。

## 実際のAPIを使う

`.env`がなければ`.env.example`をコピーして作成します。既にある場合は上書きせず、次の項目を追記・設定してください。

```dotenv
GOOGLE_POLLEN_API_KEY=ここに自分のキーを設定
```

[Google Pollenの設定手順](https://developers.google.com/maps/documentation/pollen/get-api-key)に従い、Pollen APIを有効にしたキーを使います。キーはGit・Notion・画面に載せません。

```bash
python run.py
```

気象APIと市区町村データはキー不要です。花粉キーが空でも起動できますが、その場合は**気象のみ・花粉は未取得・レベルは判定不可**になります。現在の環境ではGoogle花粉キー未設定のため、実花粉応答・植物コード対応は未検証です。返らない種類を別の分類で代用しません。

対策文は班の確認前の**授業の実演用案**です。予報の実データ／架空データとは区別して画面に表示します。Geminiは起動条件に含まれません。将来の文生成は`recommend/service.py`の`advisor`境界に追加でき、レベルはPythonで決めたままです。

## 現在地・保存設定

- 現在地はボタンを押したときだけ取得します。ブラウザーで位置情報を許可してください。
- 座標を国土地理院で市区町村に変換し、**市区町村の代表地点**を気象・花粉APIに渡します。地点ごとの実測値や自治体全域の平均とは表示しません。
- 海上など自治体を特定できない場合は都道府県・市区町村の手動選択へ切り替えます。
- 現在地は`localhost`またはHTTPSで利用します。他PCからの通常HTTPではブラウザーに拒否される場合があります。
- アレルギー設定だけを`localStorage`の`pollen-navi.settings.v1`に保存します。現在地・結果・APIキーは保存しません。
- 次回も同じブラウザープロファイルとURLを使ってください。`localhost`と`127.0.0.1`は保存先が別です。
- 「保存したアレルギー設定を削除」で消せます。保存できないブラウザーでも今回の検索は使えます。

## 判定の読み方

| UPI | レベル |
| --- | --- |
| 0〜1 | 低 |
| 2〜3 | 中 |
| 4 | 高 |
| 5 | 非常に高い |

未設定時は地域分類の最大値、設定ありでは設定した種類の有効UPI最大値を使います。一部の設定種が未取得なら暫定結果、すべて未取得なら個人向けレベルは判定不可です。地域の参考値は別表示します。風でレベルを上げません。天気・風は対策内容に使います。

気象は日本時間（Asia/Tokyo）、Google花粉はUTCの日付です。同じ暦日を照合し、別日のデータへ黙って置き換えません。両者が同じ24時間を表すものではありません。

## 構成と担当別起動

| プログラム | 起動モジュール | 接続 |
| --- | --- | --- |
| UI | `python -m streamlit run UI/app.py` | ControllerへHTTP |
| 通信制御 | `python -m server.api` | 気象・花粉へMQTT、推薦へHTTP |
| 気象 | `python -m weather.worker` | Open-Meteo取得、MQTT返信 |
| 花粉 | `python -m pollen.worker` | Google Pollen取得、MQTT返信 |
| 推薦 | `python -m recommend.api` | Python判定、HTTP返信 |
| 開発Broker | `python -m common.broker` | 127.0.0.1:1883 |

個別に起動するときはBroker→気象/花粉/推薦→Controller→UIの順です。全担当で同じ`APP_MODE=demo`または`APP_MODE=live`を環境変数に指定してください。一括起動では自動設定します。

初期ポートはMQTT 1883、Controller 8000、推薦8001、UI8501。競合時は既存アプリを停止するか、例のように変更します。

```bash
python run.py --demo --mqtt-port 1884 --controller-port 8100 --recommend-port 8101 --ui-port 8502
```

`--no-ui`では通信だけ起動します。`--external-broker`では`.env`の`MQTT_HOST`/`MQTT_PORT`にある既存Brokerを使い、ローカルBrokerを起動しません。PCを分ける場合は各担当を個別起動し、HTTP接続先・待受アドレス・Broker宛先を合わせます。複数PC実演は未検証で、必要性は先生へ確認してください。開発Brokerはローカル専用です。

## うまく動かない場合

| 表示・症状 | 確認すること |
| --- | --- |
| ポートが使用中 | 前回の一括起動をCtrl+Cで終了するか、別ポートを指定 |
| 必要なライブラリがない | 仮想環境を有効化し、`python -m pip install -r requirements.txt` |
| 通信制御・推薦に接続できない | 起動した端末の停止メッセージと宛先・ポート |
| 担当から期限内に返信なし | Worker/Brokerの起動、全担当のモード一致、MQTTの宛先 |
| 花粉キー未設定 | `.env`の`GOOGLE_POLLEN_API_KEY`を設定後、全体を再起動 |
| 指定日の花粉がない | 提供元のUTC日付と実際の利用可能日。別日へ自動変更しません |
| 市区町村一覧・代表地点が取れない | ネット接続、国土地理院の提供状況を確認し、「地域一覧を再読み込み」を押す |
| 現在地が使えない | ブラウザー権限・localhost/HTTPSを確認。都道府県・市区町村の手動選択も可能 |

Controllerは位置解決から35秒の共通期限を管理します。通常のWorker待機は20秒、MQTT接続・購読は5秒を目安に打ち切ります。外部API取得は最大8秒、位置解決は1呼出し5秒、推薦HTTPは3秒、UIのHTTP待機は55秒です。異常時にも画面で理由を表示します。

## テストと設計書

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q --ignore=env
```

外部キーなしの自動テストではHTTP fixtureと実ローカルMQTTを使います。

- [アプリ設計書](docs/pollen-navi-app-design-v0.2-2026-10-18.md)
- [今回の実装計画](docs/superpowers/plans/2026-10-18-mqtt-api-integration.md)
- [実装・検証記録](docs/implementation/2026-10-18-integration.md)

出典：[Open-Meteo](https://open-meteo.com/en/docs)、[Google Pollen](https://developers.google.com/maps/documentation/pollen/overview)、[国土地理院](https://maps.gsi.go.jp/)。花粉表示：Google Maps · Source: Includes pollen data from Google。
