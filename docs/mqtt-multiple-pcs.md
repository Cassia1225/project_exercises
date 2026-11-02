# 複数のPCでMQTTを使って動かす

このページはLAN内のMosquitto用です。HiveMQ公開BrokerのWebSocket + TLSで試す場合は、[HiveMQ検証手順](mqtt-hivemq.md)を使います。既存 `.env.lan` はそのまま保持できます。

## 1. 1台用と複数PC用の違い

今までの `python run_all.py` は、そのまま使えます。
追加した `run_role.py` は、自分の担当だけを起動するためのファイルです。
各担当のデータの作り方やMQTTの受け渡し先は、今までと共通です。

| 動かし方 | 設定ファイル | 起動方法 |
| --- | --- | --- |
| 自分のPCだけで全体を動かす | `.env` | `python run_all.py` |
| 各自のPCで担当を動かす | `.env.lan` | `python run_role.py 担当名 --env-file .env.lan` |

`.env.lan` を作っても、既存の `.env` は書き換えません。
1台用へ戻るときは、複数PC用の担当プログラムを止めて、従来の方法で起動します。

## 2. 全体の配置を決める

最初は全員が同じ、信頼できる家庭内LANなどにつながる構成で試します。
同じWi-Fiでも、学校やゲスト用ネットワークではPC同士の接続が禁止されている場合があります。

例として、次のように分けます。Brokerは、メッセージの中継所です。

| PC | 起動するもの | 担当名 |
| --- | --- | --- |
| UI担当のPC | 画面 | `ui` |
| 通信制御担当のPC | 通信制御と、全員が使うBroker | `server` |
| 花粉担当のPC | 花粉取得 | `pollen` |
| 気象担当のPC | 気象取得 | `weather` |
| 推薦担当のPC | 推薦処理 | `recommend` |

Brokerを別のPCに置いても構いません。全員が、同じ1つのBrokerを使います。
**全員のPCで `run_all.py` を動かす形にはしません。** 同じ担当が複数起動して、取得や返信が重複するためです。

## 3. 各PCの準備

全員が同じ版のコードを用意します。この手順は `main` に統合されています。古い `MQTT_各自実行版` を選ぶ必要はありません。
以下の操作は、`README.md` や `run_role.py` があるプロジェクトのフォルダーで行います。
既に仮想環境 `env` がある人は、作り直さず、その環境を使ってください。

### Mac

仮想環境がない場合だけ、最初に作ります。

```bash
python3 -m venv env
```

```bash
source env/bin/activate
python -m pip install -r requirements.txt
cp .env.lan.example .env.lan
```

### Windows（PowerShell）

仮想環境がない場合だけ、最初に作ります。

```powershell
py -m venv env
```

```powershell
.\env\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.lan.example .env.lan
```

既に `.env.lan` を編集してある場合は、コピーをやり直さずに使います。
この先の表の `python` は、Macでは仮想環境の `python`、Windowsでは `.\env\Scripts\python.exe` に読み替えます。

## 4. Brokerを動かすPCの準備

この節は、Broker担当の1人だけが行います。他の人のPCでBrokerを起動する必要はありません。

### 4-1. Mosquittoを用意する

Macで未導入なら、次を実行します。

```bash
brew install mosquitto
```

Windowsで未導入なら、[Mosquitto公式サイト](https://mosquitto.org/download/)のWindowsインストーラーで導入します。
以降のWindows例は、標準の `C:\Program Files\mosquitto` に導入した場合です。

既存のローカル用Mosquittoサービスは、そのままで構いません。
複数PC用は別ポート `1884` で起動するので、ローカル用 `1883` の設定を変更する必要はありません。

### 4-2. 全員が接続するためのパスワードを登録する

ユーザー名を `group8` とする例です。パスワードは実行後の入力欄で決めます。
入力時に文字が見えなくても正常です。

Mac:

```bash
mosquitto_passwd -c mqtt/passwords group8
```

Windows:

```powershell
& "C:\Program Files\mosquitto\mosquitto_passwd.exe" -c mqtt\passwords group8
```

`-c` はパスワードファイルを新しく作る指定です。**既存ファイルがある場合は上書きするので、更新するときは `-c` を外します。**
作成された `mqtt/passwords` と、各自の `.env.lan` はGitの対象外です。キーや実パスワードをコード、チャット、Gitに貼り付けません。

### 4-3. Broker用のターミナルを開いたまま起動する

プロジェクトのフォルダーで実行します。パスワードファイルの場所も、このフォルダーを基準にしています。

Mac:

```bash
mosquitto -c mqtt/mosquitto-lan.conf.example -v
```

Windows:

```powershell
& "C:\Program Files\mosquitto\mosquitto.exe" -c mqtt\mosquitto-lan.conf.example -v
```

このターミナルは開いたままにします。止めるときはCtrl+Cです。
`Address already in use` と表示されたら、1884を使っている別のBrokerなどを確認します。

この設定例は、同じ信頼できるLANでの学習用です。通信は暗号化されないので、最初の確認には架空のアレルギー条件を使います。インターネット向けのポート開放には使いません。離れた自宅同士で実データを扱う場合は、認証・TLS・送受信権限を備えたBrokerなどを別途用意します。架空条件での学習・検証には[HiveMQ公開Broker](mqtt-hivemq.md)も選べます。

## 5. 全員の `.env.lan` をそろえる

まず、Broker担当のPCでLAN側のIPv4アドレスを調べます。
Macは「システム設定 → ネットワーク → 使用中の接続 → 詳細 → TCP/IP」、Windowsは「設定 → ネットワークとインターネット → 使用中の接続のプロパティ」で確認できます。
Windowsでは `ipconfig` の使用中のアダプターのIPv4アドレスでも確認できます。

例としてBrokerのアドレスを `192.168.0.10` とした場合、全員の `.env.lan` を次のようにします。
これは例です。**アドレスとパスワードは、実際の値に置き換えます。**

```dotenv
MQTT_BROKER=192.168.0.10
MQTT_PORT=1884
MQTT_TRANSPORT=tcp
MQTT_WS_PATH=/mqtt
MQTT_TLS=false
MQTT_TOPIC_PREFIX=group8/project_exercises/v1
MQTT_USERNAME=group8
MQTT_PASSWORD=Brokerで登録したパスワード
GOOGLE_POLLEN_API_KEY=
```

- `MQTT_BROKER`：全員が接続する中継所の住所です。`localhost` は「今使っている自分のPC」を意味するので、別PCからの接続先には使いません。
- `MQTT_PORT`：中継所の窓口番号です。この設定例では全員 `1884` です。
- `MQTT_TOPIC_PREFIX`：全員で使う宛先名の先頭です。1文字でも違うと同じ処理につながりません。
- `MQTT_USERNAME`・`MQTT_PASSWORD`：Brokerで登録したものです。パスワードに `#` や空白がある場合は、値全体を引用符で囲みます。
- `GOOGLE_POLLEN_API_KEY`：花粉担当だけが自分の有効なキーを記入します。他の担当への配布は不要です。空欄なら花粉はダミーになり、画面にも表示されます。

この設定例は、個人PC用とはTopicの先頭も分けています。同じBroker内で試す場合も、ローカル試験と班の試験を混ぜないためです。
Broker担当のPCでファイアウォールの確認が出たら、信頼するLANからのTCP 1884接続に範囲を絞って許可します。既存のネットワーク制限で到達できない場合は、許可されたLANを使います。

## 6. 自分の担当だけを起動する

Brokerを先に起動し、次に通信制御・気象・花粉・推薦を起動します。全担当がBrokerに接続した後にUIで検索します。

| 担当 | 自分のPCで実行するコマンド |
| --- | --- |
| 通信制御 | `python run_role.py server --env-file .env.lan` |
| 気象 | `python run_role.py weather --env-file .env.lan` |
| 花粉 | `python run_role.py pollen --env-file .env.lan` |
| 推薦 | `python run_role.py recommend --env-file .env.lan` |
| UI | `python run_role.py ui --env-file .env.lan` |

Windowsの気象担当の例:

```powershell
.\env\Scripts\python.exe run_role.py weather --env-file .env.lan
```

UI担当は、自分のPCのブラウザーで `http://localhost:8501` を開きます。
他の担当のブラウザーを同時に開く必要はありません。
各担当のプログラムは、データを中継できるよう起動したままにします。
全員が同じ瞬間にコマンドを実行する必要はありません。

各担当が使うファイルは、これまでと同じです。起動用ファイルが、設定を読み取って、選んだ担当のプログラムを起動しています。

## 7. 最初の確認

UIで地域・日程を指定して「対策を調べる」を押し、各担当のターミナルで次の順に確認します。

1. 通信制御が、気象と花粉に依頼する。
2. 気象と花粉が、それぞれ依頼を受け取り、結果を返す。
3. 通信制御が、推薦へ依頼する。
4. 推薦が結果を返し、通信制御がUIへ返す。
5. UIに地域に対応した結果、または取得失敗・欠測の説明が出る。

`request_id` は検索ごとの番号です。各担当のログで同じ番号がつながっていれば、同じ検索を受け渡しています。
ダミー表示だけの成功と、実際のAPI取得に成功したことは分けて記録します。

## 8. つながらないとき

| 状況 | 最初に確認すること |
| --- | --- |
| 接続を拒否された／接続できない | Broker起動、実際のIPv4、1884、ファイアウォール、PC同士の到達性 |
| `Not authorized`／購読タイムアウト | Brokerに登録したユーザー名・パスワード、接続しているBrokerの取り違え |
| Brokerには接続できるが結果が来ない | 全担当の起動、全員のTopic先頭の一致、担当が途中で止まっていないか |
| 花粉がダミーになる | 花粉担当の `.env.lan` のAPIキー |
| API取得エラーになる | 通信制御・気象・花粉の各PCのインターネット接続、APIの応答 |

WindowsからBrokerへの接続先確認例:

```powershell
Test-NetConnection -ComputerName 192.168.0.10 -Port 1884
```

この結果が成功しても、MQTTのパスワード認証や、全担当の連携まで成功したことにはなりません。
`.env.lan` を編集したら、そのPCの担当プログラムを止めてから起動し直します。

## 9. テストと確認範囲

```bash
python -m pytest -q tests
```

担当別起動の試験は、短い確認用プログラムを実際に起動します。
`test_mqtt_network.py` は、独立したループバック用Brokerで認証・JSONの往復・別プロセスの担当連携・2利用者の結果の分離を確認します。外部APIは架空の応答です。
Mosquittoとmosquitto_passwdが見つからないPCでは、この通信試験だけをスキップします。

同じPC上の別プロセスでの確認は、複数の物理PCでの確認とは異なります。
各自のPC・Windows実機・利用するLANでの確認は、上の手順で別途行ってください。
2026-10-30に、アプリの送受信日付は `date` に統一しました。旧 `day` 入力は互換用に受け付けますが、返却には `date` だけを使います。日付キー不一致による既存2件のテスト失敗も解消済みです。

参考: [Mosquitto設定の公式説明](https://mosquitto.org/man/mosquitto-conf-5.html)、[Paho MQTTの公式説明](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html)
