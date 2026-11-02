"""UI（Streamlit）から通信制御へ、MQTTで検索を依頼する関数。"""
import queue
import sys
import threading
import uuid
from pathlib import Path

# 1つ上のフォルダー（リポジトリのルート）を読み込み先に追加する（common を使うため）
sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import mqtt_settings as ms


def ask_server(location, target_date, allergies, timeout=60):
    """検索の依頼を送り、通信制御からの結果(dict)を待って返す。

    target_date は "2026-10-20" のような文字列。
    timeout 秒たっても結果が来なければ、エラーの辞書を返す。
    """
    request_id = uuid.uuid4().hex  # この検索だけの番号
    my_result_topic = ms.result_topic_for(request_id)

    connected = threading.Event()   # 接続結果（成功・拒否）が届いたら合図する旗
    subscribed = threading.Event()  # 購読が終わったら合図する旗
    results = queue.Queue()         # 届いた結果を入れる箱
    failures = []

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            failures.append("MQTT接続が拒否されました: " + str(reason_code))
            print(f"[UI] ブローカーへの接続が拒否されました (reason_code: {reason_code})")
            connected.set()
            subscribed.set()
            return
        print(f"[UI] ブローカーに接続成功 (reason_code: {reason_code})")
        connected.set()
        # 自分の検索の返信先だけを購読する
        client.subscribe(my_result_topic, qos=1)

    def on_subscribe(client, userdata, mid, reason_codes, properties):
        if not reason_codes or any(code not in (0, 1, 2) for code in reason_codes):
            failures.append("MQTTの購読が拒否されました")
            print(f"[UI] トピックの購読が拒否されました: {my_result_topic}")
        else:
            print(f"[UI] トピックの購読完了: {my_result_topic}")
        subscribed.set()

    def on_message(client, userdata, message):
        print(f"[UI] レスポンスを受信しました: {message.topic}")
        data = ms.read_json(message)
        if (data is not None and message.topic == my_result_topic
                and data.get("request_id") == request_id
                and data.get("status") in ("success", "partial", "error")):
            results.put(data)

    client = ms.create_client("ui")
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message

    try:
        print(f"[UI] MQTTブローカー ({ms.BROKER}:{ms.PORT}) に接続試行中...")
        client.connect(ms.BROKER, ms.PORT, 60)
    except OSError as error:
        return _error("MQTTブローカーに接続できませんでした: " + str(error))

    client.loop_start()  # 受信の処理を裏で動かす
    try:
        if not connected.wait(timeout=60):
            return _error("MQTTブローカーへの接続がタイムアウトしました (60秒経過)")
        if failures:
            return _error(failures[0])
        # 返信を受け取る準備ができてから依頼を送る（先に送ると返信を取り逃す）
        if not subscribed.wait(timeout=60):
            return _error("MQTTの購読がタイムアウトしました (60秒経過)")
        if failures:
            return _error(failures[0])

        request = {
            "request_id": request_id,
            "location": location,
            "date": target_date,
            "allergies": allergies,
        }
        print(f"[UI] リクエストを送信中: {ms.TOPIC_REQUEST}")
        ms.send_json(client, ms.TOPIC_REQUEST, request)

        try:
            print(f"[UI] レスポンス待機中 (最大 {timeout} 秒)...")
            return results.get(timeout=timeout)
        except queue.Empty:
            return _error(f"結果が届きませんでした ({timeout}秒経過)。5つのプログラムが起動しているか確認してください")
    finally:
        # ここで通信を切る
        client.loop_stop()
        client.disconnect()


def _error(message):
    return {
        "status": "error",
        "data": None,
        "errors": [{"source": "ui", "code": "MQTT_ERROR", "message": message}],
    }
