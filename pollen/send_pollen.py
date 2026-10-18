"""③ 花粉プログラム（大高さん担当）

通信制御から「この場所・この日の花粉を調べて」という依頼をMQTTで受け取り、
Google Pollen APIで調べた結果をMQTTで返す。起動したら、止めるまで待ち続ける。
APIキーが .env にないときは、ダミーの値を返す（is_mock = True）。

起動方法（リポジトリのルートで）: python pollen/send_pollen.py
"""
import sys
from pathlib import Path

# 1つ上のフォルダー（リポジトリのルート）を読み込み先に追加する（common を使うため）
sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import mqtt_settings as ms
from get_pollen_data import get_pollen_info


def handle_request(request):
    """依頼1件を処理して、返信用の辞書を作る。"""
    reply = {
        "request_id": request["request_id"],
        "source": "pollen",
        "is_mock": False,
    }

    try:
        pollen, is_mock = get_pollen_info(request["latitude"], request["longitude"], request["date"])
    except Exception as error:
        print("花粉APIのエラー:", error)
        pollen = None
        is_mock = False

    if pollen is None or pollen["upi"] is None:
        reply["status"] = "error"
        reply["data"] = None
    else:
        reply["status"] = "success"
        reply["data"] = pollen
        reply["is_mock"] = is_mock

    return reply


def on_connect(client, userdata, flags, reason_code, properties):
    print("ブローカーに接続しました:", reason_code)
    client.subscribe(ms.TOPIC_POLLEN_REQUEST, qos=1)


def on_message(client, userdata, message):
    # おかしなメッセージが1件来ても、プログラム全体が止まらないようにする
    try:
        request = ms.read_json(message)
        if request is None:
            return

        print("依頼を受け取りました:", request["request_id"], request["date"])
        reply = handle_request(request)
        ms.send_json(client, ms.TOPIC_POLLEN_RESULT, reply)
        print("結果を返しました:", reply["status"])

    except Exception as error:
        print("メッセージの処理中にエラーが起きたので無視しました:", repr(error))


if __name__ == "__main__":
    client = ms.create_client("pollen")
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(ms.BROKER, ms.PORT, 60)
    print("花粉プログラムを起動しました。止めるときは Ctrl+C")
    client.loop_forever()
