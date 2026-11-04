"""取得済みの気象・花粉データを推薦関数へ渡す。"""
from .recommend import recommend, normalize_weather, _weather_display


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
    """集約処理から受け取った依頼を、既存の recommend() の入力の形に変える。

    取得に失敗した情報は None のまま渡す（recommend() がエラーとして返す）。
    """
    # 取得できなかった情報は空の辞書として読み、欠けた値は None にする。
    weather = message.get("weather") or {}
    pollen = message.get("pollen") or {}
    upi = pollen.get("upi")
    pollen_text = None if upi is None else upi_to_text(upi)

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
    weather = message.get("weather") or {}
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
        "Pollen": "指数なし",
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
