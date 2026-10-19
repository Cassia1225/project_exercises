import requests
from datetime import datetime
from dotenv import load_dotenv

from common.protocol import JST, number
from common.providers import ProviderError, request_timeout

load_dotenv()
URL = "https://api.open-meteo.com/v1/forecast"

# 単体で実行するときの東京駅周辺の座標。
# アプリから呼ぶときは、選択した市区町村の座標を引数で渡す。
latitude = 35.6812
longitude = 139.7671


def weather_data_output(
    latitude=latitude, longitude=longitude, day=None, *, session=requests, timeout=8
):
    if day is None:
        day = datetime.now(JST).date().isoformat()

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": (
            "temperature_2m_mean,"
            "wind_speed_10m_max,"
            "relative_humidity_2m_mean,"
            "weather_code"
        ),
        "start_date": day,
        "end_date": day,
        "timezone": "Asia/Tokyo",
        "wind_speed_unit": "ms",
    }

    try:
        res = session.get(URL, params=params, timeout=timeout)
        res.raise_for_status()
        data = res.json()
    except (requests.RequestException, ValueError):
        raise ProviderError(
            "API_ERROR", "気象情報を取得できませんでした。", "weather"
        ) from None

    if not isinstance(data, dict) or not isinstance(data.get("daily"), dict):
        raise ProviderError("INVALID_RESPONSE", "気象情報の形式が不正です。", "weather")
    daily = data["daily"]

    # 配列の先頭ではなく、指定した日付の位置を使う。
    dates = daily.get("time", [])
    if not isinstance(dates, list) or day not in dates:
        raise ProviderError(
            "DATE_UNAVAILABLE", "指定日の気象情報がありません。", "weather"
        )
    day_index = dates.index(day)

    def get_value(name, minimum, maximum, integer=False):
        values = daily.get(name, [])
        if not isinstance(values, list) or day_index >= len(values):
            return None
        value = values[day_index]
        if not number(value, minimum, maximum):
            return None
        if integer and type(value) is not int:
            return None
        return value

    current_obj = {
        "time": dates[day_index],
        "temperature_mean": get_value("temperature_2m_mean", -90, 60),
        "humidity_mean": get_value("relative_humidity_2m_mean", 0, 100),
        "wind_speed_max": get_value("wind_speed_10m_max", 0, 150),
        "weather_code": get_value("weather_code", 0, 99, integer=True),
        "timezone": "Asia/Tokyo",
        "units": {
            "wind_speed_max": "m/s",
            "temperature_mean": "°C",
            "humidity_mean": "%",
        },
    }

    # 異なる単位の風速や、異なるタイムゾーンの値を採用しない。
    units = data.get("daily_units")
    if not isinstance(units, dict):
        units = {}
    if units.get("wind_speed_10m_max") != "m/s":
        current_obj["wind_speed_max"] = None
    if data.get("timezone") != "Asia/Tokyo":
        raise ProviderError(
            "INVALID_TIMEZONE", "気象情報のタイムゾーンが一致しません。", "weather"
        )
    if current_obj["weather_code"] is None and current_obj["wind_speed_max"] is None:
        raise ProviderError(
            "MISSING_DATA", "指定日の天気・風速を取得できませんでした。", "weather"
        )

    missing = []
    field_names = {
        "weather_code": "天気",
        "wind_speed_max": "風速",
        "temperature_mean": "平均気温",
        "humidity_mean": "平均湿度",
    }
    for name, label in field_names.items():
        if current_obj[name] is None:
            missing.append(label)
    if missing:
        current_obj["_warnings"] = [
            {
                "source": "weather",
                "code": "MISSING_FIELDS",
                "message": "未取得：" + "、".join(missing),
            }
        ]
    return current_obj


def check_output(current_obj, daily=None):
    if daily is not None:
        print(daily)
    print("日時：", current_obj["time"])
    print("気温：", current_obj["temperature_mean"], "℃")
    print("湿度：", current_obj["humidity_mean"], "%")
    print("最大風速:", current_obj["wind_speed_max"], "m/s")


# MQTT担当との接続口。元の関数の結果を、共通のキー名に合わせる。
def get_weather(request, *, session=requests):
    current_obj = weather_data_output(
        request["latitude"],
        request["longitude"],
        request["date"],
        session=session,
        timeout=request_timeout(request),
    )
    current_obj["provider_date"] = current_obj.pop("time")
    return current_obj


if __name__ == "__main__":
    current_obj = weather_data_output()
    check_output(current_obj)
