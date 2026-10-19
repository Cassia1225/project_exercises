import requests
import json
import os
from datetime import date, datetime
from dotenv import load_dotenv

from common.protocol import ALLERGENS, JST, valid_upi
from common.providers import ProviderError, request_timeout

load_dotenv()

# APIの名前を、アプリ内で使う名前に合わせる。
CODES = {
    "TREE": "tree",
    "GRASS": "grass",
    "WEED": "weed",
    "JAPANESE_CEDAR": "sugi",
    "JAPANESE_CYPRESS": "hinoki",
    "RAGWEED": "ragweed",
    "BIRCH": "birch",
}


# 生データ取得
def get_pollen_data(
    latitude=35.6812, longitude=139.7671, *, session=requests, timeout=8
):
    url = "https://pollen.googleapis.com/v1/forecast:lookup"
    api_key = os.getenv("GOOGLE_POLLEN_API_KEY", "").strip()
    if not api_key:
        raise ProviderError(
            "MISSING_API_KEY",
            "Google Pollen APIキーが未設定です。.envを確認してください。",
            "pollen",
        )

    params = {
        "location.latitude": latitude,
        "location.longitude": longitude,
        "days": 5,
        "languageCode": "ja",
        "plantsDescription": "false",
    }

    # キーやエラー本文を画面・端末へ出力しない。
    try:
        response = session.get(
            url, params=params, headers={"X-Goog-Api-Key": api_key}, timeout=timeout
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        raise ProviderError(
            "API_ERROR", "花粉情報を取得できませんでした。", "pollen"
        ) from None


# データ成型
def format_pollen_data(raw_pollen_data, day=None):
    if day is None:
        day = datetime.now(JST).date().isoformat()
    if not isinstance(raw_pollen_data, dict):
        raise ProviderError("INVALID_RESPONSE", "花粉情報の形式が不正です。", "pollen")
    daily_info = raw_pollen_data.get("dailyInfo")
    if not isinstance(daily_info, list):
        raise ProviderError("INVALID_RESPONSE", "花粉情報の形式が不正です。", "pollen")

    # 複数日のデータから、指定した日だけを選ぶ。
    selected_day = None
    for info in daily_info:
        try:
            api_date = info["date"]
            provider_date = date(
                api_date["year"], api_date["month"], api_date["day"]
            ).isoformat()
        except (TypeError, ValueError, KeyError):
            continue
        if provider_date == day:
            selected_day = info
            break
    if selected_day is None:
        raise ProviderError(
            "DATE_UNAVAILABLE",
            "指定日の花粉情報がありません（提供元はUTC基準）。",
            "pollen",
        )
    if raw_pollen_data.get("regionCode") != "JP":
        raise ProviderError(
            "OUTSIDE_JAPAN", "花粉の取得地域が日本と一致しません。", "pollen"
        )

    # 地域分類と植物に、同じ整形処理を使う。樹木全体をスギとは扱わない。
    def format_entries(name):
        entries = selected_day.get(name, [])
        if not isinstance(entries, list):
            return []
        formatted_entries = []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("code"), str):
                continue
            provider_code = entry["code"]
            code = CODES.get(provider_code, "provider:" + provider_code)
            index_info = entry.get("indexInfo")
            if not isinstance(index_info, dict):
                index_info = {}
            upi = index_info.get("value")
            availability = "missing"
            if index_info.get("code") == "UPI" and valid_upi(upi):
                availability = "available"
            else:
                upi = None
            formatted_entries.append(
                {
                    "code": code,
                    "provider_code": provider_code,
                    "name": str(entry.get("displayName") or provider_code),
                    "upi": upi,
                    "availability": availability,
                }
            )
        return formatted_entries

    pollen_types = format_entries("pollenTypeInfo")
    plants = format_entries("plantInfo")
    present_codes = []
    has_valid_upi = False
    for entry in pollen_types + plants:
        present_codes.append(entry["code"])
        if entry["availability"] == "available":
            has_valid_upi = True

    # APIに値がなかった種類を、UPI 0で埋めない。
    for code in ("sugi", "hinoki", "ragweed", "birch", "kamogaya"):
        if code not in present_codes:
            availability = "unknown"
            if code in ("sugi", "hinoki"):
                availability = "missing"
            plants.append(
                {
                    "code": code,
                    "provider_code": None,
                    "name": ALLERGENS[code],
                    "upi": None,
                    "availability": availability,
                }
            )
    if not has_valid_upi:
        raise ProviderError(
            "MISSING_DATA", "指定日の有効な花粉指数を取得できませんでした。", "pollen"
        )

    formatted_data = {
        "provider_date": day,
        "provider_timezone": "UTC",
        "region_code": raw_pollen_data["regionCode"],
        "types": pollen_types,
        "plants": plants,
    }
    return formatted_data


# 他のから呼ばれるやつ
def get_pollen_info(
    latitude=35.6812, longitude=139.7671, day=None, *, session=requests, timeout=8
):
    raw_pollen_data = get_pollen_data(
        latitude, longitude, session=session, timeout=timeout
    )
    result = format_pollen_data(raw_pollen_data, day)
    return result


# MQTTとの接続。共通の要求から、元の関数へ引数を渡す。
def get_pollen(request, *, session=requests):
    return get_pollen_info(
        request["latitude"],
        request["longitude"],
        request["date"],
        session=session,
        timeout=request_timeout(request),
    )


# テスト用
if __name__ == "__main__":
    output = get_pollen_data(35.6812, 139.7671)
    print("テスト結果")
    pretty_json = json.dumps(output, indent=2, ensure_ascii=False)
    print(pretty_json)
