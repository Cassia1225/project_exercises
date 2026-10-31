# HiveMQ公開Brokerを使って複数PCで検証する

## 接続先と用途

自宅の2台PCで確認した接続方式を、花粉対策ナビの5役で選べます。

| 項目 | HiveMQ検証用 | ローカルMosquitto | LAN Mosquitto |
| --- | --- | --- | --- |
| 設定ファイル | `.env.hivemq` | `.env` | `.env.lan` |
| Broker | `broker.hivemq.com` | `localhost` | Broker担当PCのIPv4 |
| ポート | `8884` | `1883` | 見本では`1884` |
| MQTT_TRANSPORT | `websockets` | `tcp` | `tcp` |
| MQTT_WS_PATH | `/mqtt` | 使用しない | 使用しない |
| MQTT_TLS | `true` | `false` | 見本では`false` |
| 認証 | 不要・空欄 | 通常は空欄 | Brokerに登録した値 |

**HiveMQ公開Brokerは学習・検証専用です。** TLSはBrokerまでの通信を暗号化しますが、同じTopicを他者が購読・送信することを防ぎません。APIキー、パスワード、トークン、氏名、連絡先、実際のアレルギー、精密な現在地などをPublishしないでください。入力した地域・日付・アレルギー条件もMQTT本文に入るため、個人と結び付かない一般的な地域と架空の条件を使います。

設定やAPIキーを自動でpayloadに含める処理はありませんが、入力中の秘密情報を自動検出・除去する機能はありません。公開メッセージは第三者からのものも届き得るため、結果を信頼性のある本番サービスとして利用しません。公開サービスの停止やメッセージ損失もあり得ます。

## 1. 全PCに同じコードと設定を用意する

既存の仮想環境を使い、必要に応じて依存ライブラリを入れます。

```bash
python -m pip install -r requirements.txt
```

初回だけ、見本をコピーします。既に作った設定ファイルは上書きせず編集します。

Mac:

```bash
cp .env.hivemq.example .env.hivemq
```

Windows PowerShell:

```powershell
Copy-Item .env.hivemq.example .env.hivemq
```

`.env.hivemq` の内容は次のとおりです。

```dotenv
MQTT_BROKER=broker.hivemq.com
MQTT_PORT=8884
MQTT_TRANSPORT=websockets
MQTT_WS_PATH=/mqtt
MQTT_TLS=true
MQTT_TOPIC_PREFIX=group8/hivemq-test/replace-with-shared-random-id/v1
MQTT_USERNAME=
MQTT_PASSWORD=
GOOGLE_POLLEN_API_KEY=
```

`replace-with-shared-random-id` を、班で決めた十分長いランダムIDへ変更し、**全PCで同じprefix**を使います。担当ごとに異なるIDを生成してはいけません。代表者1人が次のコマンドで生成し、同じ値を全員へ共有できます。

```bash
python -c "import uuid; print('group8/hivemq-test/' + uuid.uuid4().hex + '/v1')"
```

ランダムprefixは他の利用者との混線を減らす名前です。秘密保持やアクセス制御にはなりません。Topicの末尾（`/request`、`/weather/request`等）とJSON形式は従来どおりです。

認証とAPIキーは空欄のままにします。空欄を削除すると、ターミナルや既存 `.env` の値が補われる場合があります。最初はダミー花粉で確認します。`.env.hivemq` はGit対象外、見本の `.env.hivemq.example` のみ共有対象です。既存 `.env` / `.env.lan` は変更不要です。

## 2. 2台のPCで担当を分けて起動する

例：PC Aは通信制御・気象・花粉、PC Bは推薦・UIを動かします。それぞれ別のターミナルを使い、リポジトリのルートから実行します。全PCが同じBrokerとprefixを使います。各担当は全体で1つずつ起動します。

Macでは先に仮想環境を有効化します。

```bash
source env/bin/activate
```

Windowsでは以下の `python` を `.\env\Scripts\python.exe` に読み替えられます。

PC A：

```bash
python run_role.py server --env-file .env.hivemq
```

```bash
python run_role.py weather --env-file .env.hivemq
```

```bash
python run_role.py pollen --env-file .env.hivemq
```

PC B：

```bash
python run_role.py recommend --env-file .env.hivemq
```

```bash
python run_role.py ui --env-file .env.hivemq
```

公開Brokerを使うため、Mosquittoの起動やルーターのポート開放は不要です。両PCからインターネットへ接続できる必要があります。全役の購読準備ができてから、PC Bのブラウザーで通常 `http://localhost:8501` を開き、一般的な地域と架空の条件で検索します。所在地理・気象APIには実通信します。花粉のキーが空ならダミーです。

全員が `run_all.py` を動かすと担当が重複するため、この分担時は使いません。設定を直したら対象の担当を停止して起動し直します。

## 3. 結果の確認と切替

通信制御→気象・花粉→通信制御→推薦→通信制御→UIの順で、同じ `request_id` のログと結果を確認します。接続成功だけで全連携成功とは判断しません。UIの購読待ちは10秒、結果待ちは既定30秒、keepaliveは60秒です。QoSは1、retainは無効で、接続し直すとon_connectで再購読します。

| 症状 | 確認する内容 |
| --- | --- |
| 接続できない | host・8884・websockets・/mqtt・TLS=true、ネットワークの外向き接続制限 |
| TLS証明書エラー | PCの日時、Python/OSの信頼済み証明書。証明書検証を無効にして回避しない |
| WebSocketエラー | transportの綴り、path、ポート、プロキシやネットワークの対応 |
| 結果が来ない | 全5役の起動と購読、prefixの一致、担当の重複や途中終了 |
| 花粉がダミー | キー空欄時の正常動作。実API成功とは区別する |

切り替えるときは、先に検証用の全役をCtrl+Cで停止します。

- ローカル：ローカルMosquittoを起動し、`.env` を `localhost:1883`・`MQTT_TRANSPORT=tcp`・`MQTT_TLS=false` にして、従来どおり `python run_all.py`。
- LAN：既存のLAN Brokerを起動し、全員 `python run_role.py 担当名 --env-file .env.lan`。[LAN用の手順](mqtt-multiple-pcs.md)を参照。

古い設定ファイルで新3項目が省略されていれば、既定はTCP・TLSなし・path `/mqtt` です。ただし、ターミナルの環境変数や既存 `.env` に新項目がある場合、省略した項目にはその値が使われます。不要な環境変数を解除するか、選ぶローカル/LAN用ファイルにも `MQTT_TRANSPORT=tcp`・`MQTT_TLS=false` を明示します。

## 4. テストと検証範囲

通常の全管理テスト：

```bash
python -m pytest -q tests recommend/test_recommend.py
```

公開HiveMQの実通信テストは、通常はスキップします。明示実行する場合：

Mac:

```bash
RUN_HIVEMQ_TEST=1 python -m pytest -q tests/test_hivemq_public.py
```

Windows PowerShell:

```powershell
$env:RUN_HIVEMQ_TEST="1"
python -m pytest -q tests/test_hivemq_public.py
Remove-Item Env:RUN_HIVEMQ_TEST
```

この公開試験はランダムprefixを毎回生成し、全5役の実MQTTクライアントで往復します。外部の地理・気象・花粉APIを固定の架空応答に置き換え、認証情報も空にします。独立した4役のクライアントとUIを同じPythonプロセスで動かす試験であり、物理2台PCでの確認やStreamlit画面の操作試験とは異なります。

2026-10-30の確認結果：新設定・既存通信契約25件成功。同日の日付統一後は全管理テスト108件成功・失敗0件・公開試験1件通常スキップ。公開試験を明示実行して、dateへの統一後も1件成功（12.17秒）。既存のローカルMosquitto試験では、認証・無認証・誤パスワード拒否・別プロセス連携・結果分離・海外地域の経路を確認しました。

HiveMQ対応時に残っていた推薦の `data.day` とテストの `data.date` の不一致2件は、その後の本人の統一依頼により修正しました。正式な送受信・正常/部分成功結果は `date` に統一しています。旧 `day` は入力時の互換用にのみ受け付け、両方に有効な値がある場合は `date` を優先します。修正版の物理2台PC・Windows実機・学内ネットワーク、地理/気象/花粉の実APIを含む一連の画面操作は未検証です。ユーザー提供の「自宅2台PCで接続できた」という結果と今回の検証を区別します。

## 公式資料

- [HiveMQ公開Brokerの接続情報](https://hivemq.mqtt-dashboard.com/)
- [HiveMQ公開Brokerの案内](https://www.hivemq.com/mqtt/public-mqtt-broker/)
- [Paho Python Client：transport・ws_set_options・tls_set](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html)
