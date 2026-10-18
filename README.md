プロジェクト演習の開発で使用するリポジトリです。

##ブランチ

main : 最終統合先
develop : 最終統合前に結合テストを行うブランチ
feature/api_kafun : 花粉情報にまつわる機能開発用
feature/api_weather : 気象情報にまつわる機能開発
feature/logic : 推薦システム機能開発
feature/view : UI用の開発ブランチ

## 動かし方（MQTT版・最低限の動作）

5つのプログラムがMQTTでつながり、Streamlitの画面に外出対策を表示します。

```
UI(①) ─request→ 通信制御(②) ─┬→ 気象(④)  ─┐
  ↑                         └→ 花粉(③)  ─┴→ 通信制御(②) → 推薦(⑤) → 通信制御(②) ─result→ UI(①)
```

| 担当 | ファイル | 役割 |
| --- | --- | --- |
| ① UI | `UI/app.py`, `UI/mqtt_client.py` | 地域・日付を選んで依頼し、結果を表示 |
| ② 通信制御 | `server/server.py` | 地域名→緯度経度、気象・花粉への依頼、結果の集約、推薦への依頼 |
| ③ 花粉 | `pollen/send_pollen.py`, `pollen/get_pollen_data.py` | Google Pollen APIで花粉指数(UPI)を取得 |
| ④ 気象 | `weather/send_weather.py`, `weather/get_weather_data.py` | Open-Meteoで天気・風速を取得 |
| ⑤ 推薦 | `recommend/send_recommend.py`, `recommend/recommend.py` | レベル・対策・理由を決める |
| 共通 | `common/mqtt_settings.py`, `common/locations.py`, `common/municipalities.json` | ブローカー・トピック名、都道府県・市区町村の一覧と座標の検索（国土地理院） |

### 1. 準備（最初の1回）

```
python3 -m venv env            # 仮想環境 env を作る
source env/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env           # キーなどは .env にだけ書く（.env.example には書かない）
```

### 2. 起動（ターミナルを5つ開き、リポジトリのルートで1つずつ）

どのターミナルでも、先に `source env/bin/activate` を実行してから起動します。

```
python server/server.py
python weather/send_weather.py
python pollen/send_pollen.py
python recommend/send_recommend.py
streamlit run UI/app.py
```

ブラウザーで地域と日程を選び「対策を調べる」を押すと結果が出ます。止めるときは各ターミナルで Ctrl+C。

### 注意

- ブローカーの既定は公開テスト用の `broker.hivemq.com` です。誰でも読めるので、秘密の情報は送らないでください。
  自分のPCで動かす場合は Mosquitto を入れて `.env` の `MQTT_BROKER=localhost` にします。
- `GOOGLE_POLLEN_API_KEY` がないときは花粉がダミーの値になり、画面に「ダミー」と表示されます。
- 花粉の指数が出ていない日（シーズン外など）は、レベルを「判定不可」にして天気と風だけを表示します。
- 地域の座標は、通信制御が国土地理院の住所検索で調べます（インターネット接続が必要）。
- テスト: `python -m pytest -q tests`（推薦のテストは `cd recommend && python -m pytest -q test_recommend.py`）
