"""② 通信制御プログラム（村岡さん担当）

全体のまとめ役。MQTTで次の順にメッセージを中継する。

  1. UI から検索の依頼を受け取る
  2. 地域名を緯度・経度に変えて、気象・花粉プログラムへ依頼を送る
  3. 気象・花粉の両方の結果がそろったら、推薦プログラムへ送る
  4. 推薦の結果を UI へ返す

どの検索の結果かは request_id（検索ごとの番号）で見分ける。

起動方法（リポジトリのルートで）: python server/server.py
"""
import sys
from pathlib import Path

# 1つ上のフォルダー（リポジトリのルート）を読み込み先に追加する（common を使うため）
sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import mqtt_settings as ms
from common.locations import find_location

# 処理中の検索を request_id ごとに覚えておく辞書
# 例: {"abc123": {"ui_request": {...}, "weather": None, "pollen": {...}}}
waiting = {}


def make_worker_request(ui_request, place):
    """気象・花粉プログラムへ送る依頼を作る（アレルギー情報は送らない）。"""
    return {
        "request_id": ui_request["request_id"],
        "location": place["name"],
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "date": ui_request["date"],
    }


def make_recommend_request(ui_request, weather_result, pollen_result):
    """気象と花粉の結果をまとめて、推薦プログラムへ送る依頼を作る。"""
    return {
        "request_id": ui_request["request_id"],
        "location": ui_request["location"],
        "date": ui_request["date"],
        "allergies": ui_request.get("allergies", []),
        "weather": weather_result["data"],  # 失敗していれば None
        "pollen": pollen_result["data"],    # 失敗していれば None
    }


def make_error_reply(request_id, message):
    """UIへ返すエラーの形（共通仕様の status / errors に合わせる）。"""
    return {
        "request_id": request_id,
        "status": "error",
        "data": None,
        "errors": [{"source": "server", "code": "INVALID_INPUT", "message": message}],
    }


# ---------- 受け取ったメッセージごとの処理 ----------

def on_ui_request(client, request):
    """1. UIから検索の依頼が来たとき"""
    request_id = request["request_id"]
    place = find_location(request["location"])

    if place is None:
        reply = make_error_reply(request_id, "対応していない地域です: " + request["location"])
        ms.send_json(client, ms.result_topic_for(request_id), reply)
        return

    waiting[request_id] = {"ui_request": request, "weather": None, "pollen": None}

    # 2. 気象と花粉へ、同じ内容の依頼を同時に送る
    worker_request = make_worker_request(request, place)
    ms.send_json(client, ms.TOPIC_WEATHER_REQUEST, worker_request)
    ms.send_json(client, ms.TOPIC_POLLEN_REQUEST, worker_request)
    print("気象・花粉へ依頼しました:", request_id)


def on_worker_result(client, result):
    """気象または花粉の結果が来たとき"""
    request_id = result["request_id"]
    if request_id not in waiting:
        return  # 知らない検索（他の人の検索や、終わった検索）の結果は無視

    entry = waiting[request_id]
    entry[result["source"]] = result  # source は "weather" か "pollen"

    # 3. 両方そろったら、推薦プログラムへ送る
    if entry["weather"] is not None and entry["pollen"] is not None:
        message = make_recommend_request(entry["ui_request"], entry["weather"], entry["pollen"])
        ms.send_json(client, ms.TOPIC_RECOMMEND_REQUEST, message)
        print("推薦へ依頼しました:", request_id)


def on_recommend_result(client, response):
    """4. 推薦の結果が来たとき → UIへ返す"""
    request_id = response["request_id"]
    if request_id not in waiting:
        return

    entry = waiting.pop(request_id)  # この検索はこれで終わりなので、辞書から消す
    response["pollen_is_mock"] = entry["pollen"].get("is_mock", False)
    ms.send_json(client, ms.result_topic_for(request_id), response)
    print("UIへ結果を返しました:", request_id, response["status"])


# ---------- MQTTの設定 ----------

def on_connect(client, userdata, flags, reason_code, properties):
    print("ブローカーに接続しました:", reason_code)
    client.subscribe(ms.TOPIC_REQUEST, qos=1)
    client.subscribe(ms.TOPIC_WEATHER_RESULT, qos=1)
    client.subscribe(ms.TOPIC_POLLEN_RESULT, qos=1)
    client.subscribe(ms.TOPIC_RECOMMEND_RESULT, qos=1)


def on_message(client, userdata, message):
    data = ms.read_json(message)
    if data is None:
        return

    # どのトピックに届いたかで、処理を分ける
    if message.topic == ms.TOPIC_REQUEST:
        on_ui_request(client, data)
    elif message.topic in (ms.TOPIC_WEATHER_RESULT, ms.TOPIC_POLLEN_RESULT):
        on_worker_result(client, data)
    elif message.topic == ms.TOPIC_RECOMMEND_RESULT:
        on_recommend_result(client, data)


if __name__ == "__main__":
    client = ms.create_client("server")
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(ms.BROKER, ms.PORT, 60)
    print("通信制御プログラムを起動しました。止めるときは Ctrl+C")
    client.loop_forever()
