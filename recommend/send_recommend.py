"""⑤ 推薦プログラム（高野さん担当）

通信制御から、気象と花粉の結果をまとめた依頼をMQTTで受け取り、
recommend.py の recommend() で対策を決めて、MQTTで返す。

起動方法（リポジトリのルートで）: python recommend/send_recommend.py
"""
import sys
from pathlib import Path

# 1つ上のフォルダー（リポジトリのルート）を読み込み先に追加する（common を使うため）
sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import mqtt_settings as ms
# _weather_display は recommend.py の中の関数（天気コード → 日本語）を借りて使う
from recommend import recommend, normalize_weather, _weather_display


def upi_to_text(upi):
    """花粉指数(UPI 0〜5)を、recommend() が読める日本語に変える。

    区分は設計書の表（0〜1=低、2〜3=中、4=高、5=非常に高い）に合わせた。
    """
    if upi <= 1:
        word = "少ない"
    elif upi <= 3:
        word = "やや多い"
    elif upi == 4:
        word = "多い"
    else:
        word = "非常に多い"
    return f"{word}（UPI {upi}/5）"


def make_recommend_input(message):
    """MQTTで受け取った依頼を、既存の recommend() の入力の形に変える。

    取得に失敗した情報は None のまま渡す（recommend() がエラーとして返す）。
    """
    weather = message.get("weather")
    pollen = message.get("pollen")

    # 取得に失敗していると None なので、空の辞書にしておく（.get が使えるように）
    if weather is None:
        weather = {}
    if pollen is None:
        pollen = {}

    if pollen.get("upi") is None:
        pollen_text = None
    else:
        pollen_text = upi_to_text(pollen["upi"])

    # 指数が2以上（やや多い以上）の種類だけを「飛んでいる花粉」として渡す
    flying_types = []
    for code, value in pollen.get("types", {}).items():
        if value is not None and value >= 2:
            flying_types.append(code.lower())  # 例: "WEED" → "weed"

    return {
        "request_id": message["request_id"],
        "location": message["location"],
        "date": message["date"],
        "Pollen": pollen_text,
        "weather": weather.get("weather_code"),
        "Wind": weather.get("wind_speed_max"),
        "pollen_types": flying_types,
        "user": {"allergies": message.get("allergies", [])},
    }


def make_no_pollen_response(message):
    """花粉の指数が出ていない日（シーズン外など）の結果を作る。

    指数がないのに「少ない」とは言えないので、レベルは「判定不可」にして、
    取得できた天気と風だけを表示する。status は一部だけ取得できた "partial"。
    """
    weather = message.get("weather")
    if weather is None:
        weather = {}
    code = weather.get("weather_code")
    wind = weather.get("wind_speed_max")

    if code is None:
        weather_text = "取得できませんでした"
    else:
        weather_text = _weather_display(code, normalize_weather(code))

    if wind is None:
        wind_text = "取得できませんでした"
    else:
        wind_text = str(wind) + " m/s"

    data = {
        "location": message["location"],
        "date": message["date"],
        "level": "判定不可",
        "Pollen": "指数なし",#（この日は花粉の予報データがありません）
        "weather": weather_text,
        "Wind": wind_text,
        "items": [],
        "reason": "花粉の指数が提供されていないため、対策レベルは判定できません",
    }
    return {
        "request_id": message["request_id"],
        "status": "partial",
        "data": data,
        "errors": [],
    }


def make_response(message):
    """依頼1件から、UIへ返す結果を作る。"""
    pollen = message.get("pollen")

    # 花粉の取得は成功したが、指数が1つも出ていない場合
    if pollen is not None and pollen.get("upi") is None:
        return make_no_pollen_response(message)

    # ふつうの場合は、既存の recommend() に任せる
    return recommend(make_recommend_input(message))


def on_connect(client, userdata, flags, reason_code, properties):
    print("ブローカーに接続しました:", reason_code)
    client.subscribe(ms.TOPIC_RECOMMEND_REQUEST, qos=1)


def on_message(client, userdata, message):
    # おかしなメッセージが1件来ても、プログラム全体が止まらないようにする
    try:
        request = ms.read_json(message)
        if request is None:
            return

        print("依頼を受け取りました:", request["request_id"])
        response = make_response(request)
        ms.send_json(client, ms.TOPIC_RECOMMEND_RESULT, response)
        print("結果を返しました:", response["status"])

    except Exception as error:
        print("メッセージの処理中にエラーが起きたので無視しました:", repr(error))


if __name__ == "__main__":
    client = ms.create_client("recommend")
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(ms.BROKER, ms.PORT, 60)
    print("推薦プログラムを起動しました。止めるときは Ctrl+C")
    client.loop_forever()
