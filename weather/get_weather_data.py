import requests

URL = "https://api.open-meteo.com/v1/forecast"


def get_weather(latitude, longitude, target_date):
    """Open-Meteoから、指定した場所・日付の天気（1日単位）を取得する。

    target_date は "2026-10-20" のような文字列。
    戻り値は pick_day() と同じ形の辞書。その日のデータがなければ None。
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": (
            "weather_code,"
            "wind_speed_10m_max,"
            "temperature_2m_mean,"
            "relative_humidity_2m_mean"
        ),
        "wind_speed_unit": "ms",  # 風速を m/s で受け取る（共通仕様）
        "timezone": "Asia/Tokyo",
        "start_date": target_date,
        "end_date": target_date,
    }

    res = requests.get(URL, params=params, timeout=8)
    res.raise_for_status()
    data = res.json()

    return pick_day(data["daily"], target_date)


def pick_day(daily, target_date):
    """APIの daily データから、target_date の日の値だけを取り出す。"""
    if target_date not in daily["time"]:
        return None

    # 何番目がその日のデータかを調べる
    i = daily["time"].index(target_date)

    current_obj = {
        "weather_code": daily["weather_code"][i],
        "wind_speed_max": daily["wind_speed_10m_max"][i],
        "temperature_mean": daily["temperature_2m_mean"][i],
        "humidity_mean": daily["relative_humidity_2m_mean"][i],
    }
    return current_obj


def check_output(current_obj):
    print("天気コード：", current_obj["weather_code"])
    print("気温：", current_obj["temperature_mean"], "℃")
    print("湿度：", current_obj["humidity_mean"], "%")
    print("最大風速:", current_obj["wind_speed_max"], "m/s")


# テスト用（東京駅周辺の今日の天気を表示する）
if __name__ == "__main__":
    from datetime import date

    result = get_weather(35.6812, 139.7671, date.today().isoformat())
    check_output(result)
