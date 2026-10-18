import json
import os
from datetime import date

import requests
from dotenv import load_dotenv

# APIキーはコードに書かず、.env の GOOGLE_POLLEN_API_KEY から読む
load_dotenv()
API_KEY = os.getenv("GOOGLE_POLLEN_API_KEY")

URL = "https://pollen.googleapis.com/v1/forecast:lookup"


# 生データ取得
def get_pollen_data(latitude, longitude, days):
    params = {
        "key": API_KEY,
        "location.latitude": latitude,
        "location.longitude": longitude,
        "days": days,  # 今日から何日分を取るか（1〜5）
        "languageCode": "ja",
        "plantsDescription": False,
    }

    response = requests.get(URL, params=params, timeout=8)
    print(f"HTTPステータスコード: {response.status_code}")
    response.raise_for_status()
    return response.json()


# データ成型
def format_pollen_data(raw_pollen_data, target_date):
    """Googleの返答から、target_date の日の花粉指数(UPI 0〜5)を取り出す。

    戻り値の例: {"upi": 4, "types": {"GRASS": 2, "TREE": None, "WEED": 4}}
    upi は種類ごとの値のうち一番大きいもの。値が1つもなければ None。
    """
    types = {}

    for day_info in raw_pollen_data.get("dailyInfo", []):
        d = day_info["date"]
        day_text = f"{d['year']:04d}-{d['month']:02d}-{d['day']:02d}"
        if day_text != target_date:
            continue

        # その日の、種類（樹木・イネ科・雑草）ごとの指数を集める
        for type_info in day_info.get("pollenTypeInfo", []):
            if "indexInfo" in type_info:
                types[type_info["code"]] = type_info["indexInfo"]["value"]
            else:
                types[type_info["code"]] = None  # 値なし（0とは区別する）

    values = [v for v in types.values() if v is not None]
    if len(values) == 0:
        upi = None
    else:
        upi = max(values)

    return {"upi": upi, "types": types}


def make_dummy_data():
    """APIキーがないときに使う、動作確認用の決まった値。"""
    return {"upi": 3, "types": {"GRASS": 1, "TREE": 0, "WEED": 3}}


# 他のから呼ばれるやつ
def get_pollen_info(latitude, longitude, target_date):
    """(結果の辞書, ダミーかどうか) を返す。"""
    if not API_KEY:
        print("GOOGLE_POLLEN_API_KEY がないので、ダミーの花粉データを使います")
        return make_dummy_data(), True

    # 例: 今日なら1日分、明後日なら3日分を取る
    days = (date.fromisoformat(target_date) - date.today()).days + 1
    days = min(max(days, 1), 5)

    raw_pollen_data = get_pollen_data(latitude, longitude, days)
    return format_pollen_data(raw_pollen_data, target_date), False


# テスト用
if __name__ == "__main__":
    output, is_dummy = get_pollen_info(35.6812, 139.7671, date.today().isoformat())
    print("テスト結果（ダミー）" if is_dummy else "テスト結果")
    print(json.dumps(output, indent=2, ensure_ascii=False))
