"""④ 気象プログラム（池田さん担当）

通信制御から「この場所・この日の天気を調べて」という依頼をMQTTで受け取り、
Open-Meteoで調べた結果をMQTTで返す。起動したら、止めるまで待ち続ける。

起動方法（リポジトリのルートで）: python weather/send_weather.py
"""
import sys
from pathlib import Path

# 1つ上のフォルダー（リポジトリのルート）を読み込み先に追加する（common を使うため）
sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import mqtt_settings as ms
from get_weather_data import get_weather


def handle_request(request):
    """依頼1件を処理して、返信用の辞書を作る。"""
    reply = {
        "request_id": request["request_id"],
        "source": "weather",
    }

    try:
        weather = get_weather(request["latitude"], request["longitude"], request["date"])
    except Exception as error:
        # 通信エラーなど。原因を表示して、失敗として返す
        print("気象APIのエラー:", error)
        weather = None

    if weather is None:
        reply["status"] = "error"
        reply["data"] = None
    else:
        reply["status"] = "success"
        reply["data"] = weather

    return reply


def on_connect(client, userdata, flags, reason_code, properties):
    print("ブローカーに接続しました:", reason_code)
    # 接続できたら、依頼のトピックを購読する（再接続したときもここが呼ばれる）
    client.subscribe(ms.TOPIC_WEATHER_REQUEST, qos=1)


def on_message(client, userdata, message):
    request = ms.read_json(message)
    if request is None:
        return

    print("依頼を受け取りました:", request["request_id"], request["date"])
    reply = handle_request(request)
    ms.send_json(client, ms.TOPIC_WEATHER_RESULT, reply)
    print("結果を返しました:", reply["status"])


if __name__ == "__main__":
    client = ms.create_client("weather")
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(ms.BROKER, ms.PORT, 60)
    print("気象プログラムを起動しました。止めるときは Ctrl+C")
    client.loop_forever()
