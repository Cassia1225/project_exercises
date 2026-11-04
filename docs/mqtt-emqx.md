# EMQXで花粉対策ナビを試す

## 接続設定

EMQ公式の公開Broker `broker.emqx.io` を、ポート `8084`・WebSocket＋TLS・パス `/mqtt` で使います。TLSの証明書・ホスト名検証を有効にします。

公開Brokerは他者も購読・送信できるデモ用です。文字列試験もアプリ検索も架空の条件を使い、APIキー、パスワード、氏名、実際のアレルギー、精密な現在地等を送信しません。ランダムTopicは混線を減らす名前で、秘密保持の仕組みではありません。

## 1. 文字列の疎通を確認する

リポジトリのルートで、既存のPython仮想環境を有効にします。

Mac:

```bash
source env/bin/activate
```

同じPCの自己往復試験：

```bash
python mqtt_test.py
```

2台で試す場合は、受信PCで先に次を実行します。

```bash
python recieve.py
```

購読が成功したことを確認してから、送信PCで次を実行します。

```bash
python send.py
```

架空の短い文字列を入力し、受信PCにも同じ内容が表示されることを確認します。送信側の終了は `exit`、受信側はCtrl+Cです。ファイル名は既存の `recieve.py` のままです。

この3ファイルはEMQX接続先を直接指定しています。`.env.emqx` は読みません。2台は同じBroker・ポートと同じ `TOPIC` にそろえます。`mqtt_test.py` は試行ごとに専用のランダムTopicを使い、自分自身に送信する試験です。送信側のBrokerへの送信確認だけで受信PCの表示まで成功したとは判断しません。

Windowsは上の `python` を `.\env\Scripts\python.exe` に置き換えられます。

## 2. アプリ用の設定を作る

`.env.emqx` がないPCだけ、見本をコピーします。既にある場合は内容を確認して使います。

Mac:

```bash
cp .env.emqx.example .env.emqx
```

Windows PowerShell:

```powershell
Copy-Item .env.emqx.example .env.emqx
```

```dotenv
MQTT_BROKER=broker.emqx.io
MQTT_PORT=8084
MQTT_TRANSPORT=websockets
MQTT_WS_PATH=/mqtt
MQTT_TLS=true
MQTT_TOPIC_PREFIX=group8/emqx-test/replace-with-shared-random-id/v1
MQTT_USERNAME=
MQTT_PASSWORD=
GOOGLE_POLLEN_API_KEY=
```

代表者1人だけが次でprefixを作り、`MQTT_TOPIC_PREFIX` の値として全員へ同じ値を共有します。PCごとに別の値を生成すると通信できません。`replace-with-shared-random-id` のままで共有試験をしません。

```bash
python -c "import uuid; print('group8/emqx-test/' + uuid.uuid4().hex + '/v1')"
```

このMacにLが新規作成した `.env.emqx` があれば、代表者用のランダム値を設定済みです。自分たちで決めた共通値がある場合はそれへそろえます。見本ファイルには実キーを書かず、個人設定の `.env.emqx` はGit対象外です。

認証値と花粉APIキーの空欄はそのまま残します。親の環境変数や既存 `.env` の値を引き継がないためです。初回の花粉はダミーであり、実API成功ではありません。地域検索と気象は通常のアプリではインターネット接続を使います。

## 3. 各担当を起動する

全PCにこのブランチの同じコードと共通設定を用意します。各担当は班全体で1つずつ、別ターミナルで起動します。4担当を先に起動し、UIは最後に起動します。

```bash
python run_role.py server --env-file .env.emqx
python run_role.py weather --env-file .env.emqx
python run_role.py pollen --env-file .env.emqx
python run_role.py recommend --env-file .env.emqx
python run_role.py ui --env-file .env.emqx
```

UI担当のブラウザーで `http://localhost:8501` を開き、一般的な地域と架空のアレルギー条件で検索します。同じ `request_id` で気象・花粉・推薦を経由し、UIに結果が戻ることを確認します。

`run_role.py` は `--env-file` を省略すると従来の `.env` を読みます。`run_all.py` も従来のローカル用です。このEMQX試験では上の担当別コマンドを使います。設定を変更したら対象担当を停止して起動し直します。

## 4. テスト

通常の試験は公開Brokerへの接続を行いません。ローカルMosquittoによる通信試験も含みます。

```bash
python -m pytest -q
```

公開EMQXで全5役を往復する試験だけを実行する場合：

Mac:

```bash
RUN_EMQX_TEST=1 python -m pytest -q tests/test_emqx_public.py
```

Windows PowerShell:

```powershell
$env:RUN_EMQX_TEST="1"
python -m pytest -q tests/test_emqx_public.py
Remove-Item Env:RUN_EMQX_TEST
```

ランダムTopic・架空データ・空の認証値で、地理/気象/花粉の外部APIだけを固定応答にします。実MQTTの全役往復を試しますが、物理2台や実API・画面操作の成功とは別です。

## 5. 接続できない場合

- `getaddrinfo` のエラー：接続先の名前解決で失敗しています。TLSやMQTTより前です。
- `socket.connect` のタイムアウト：TCP8084へ到達していません。同じPCを別の許可された回線へ切り替えて比較します。
- TLSエラー：PC時刻と信頼済みCAを確認します。証明書検証は無効にしません。
- 接続後に応答なし：全役の起動・購読と、Broker・ポート・prefixの一致を確認します。

EMQXへ変えても、eduroamから接続できることは保証できません。実際に使う回線でDNS→TCP8084→TLS/WebSocket→MQTT送受信を確認します。

## 公式資料

- [EMQ公開Brokerの接続情報](https://www.emqx.com/en/mqtt/public-mqtt5-broker)
- [Paho MQTT Client API](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html)
