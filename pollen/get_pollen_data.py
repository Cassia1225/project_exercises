import requests
import json
import config  # APIキー


# 生データ取得
def get_pollen_data(latitude, longitude):

    url = "https://pollen.googleapis.com/v1/forecast:lookup"

    params = {
        "key": config.API_KEY,
        "location.latitude": latitude,
        "location.longitude": longitude,
        "days": 5,
        "languageCode": "ja",
        "plantsDescription": True
    }

    response = requests.get(url, params=params)

    print(f"HTTPステータスコード: {response.status_code}")

    if response.status_code == 200:
        return response.json()
    else:
        print("エラー内容:", response.text)
        return None

# データ成型
def format_pollen_data(raw_pollen_data, target_day):

    # 一致する日付を探す
    matched_day = None
    for day in raw_pollen_data.get("dailyInfo", []):
        d = day.get("date", {})
        date_str = f"{d.get('year')}-{d.get('month'):02d}-{d.get('day'):02d}"

        if date_str == target_day:
            matched_day = day
            break

    if not matched_day:
        return {"error": "DATE_UNAVAILABLE"}

    # typesの整形
    types_list = []
    for p_type in matched_day.get("pollenTypeInfo", []):
        code = p_type.get("code")
        index_info = p_type.get("indexInfo")

        if index_info and "value" in index_info:
            upi = index_info["value"]
            availability = "available"
        else:
            upi = None
            availability = "missing"

        types_list.append({
            "code": code,
            "upi": upi,
            "availability": availability
        })

    # plantsの整形
    plants_list = []
    for plant in matched_day.get("plantInfo", []):
        code = plant.get("code")
        index_info = plant.get("indexInfo")

        if index_info and "value" in index_info:
            upi = index_info["value"]
            availability = "available"
        else:
            upi = None
            availability = "missing"

        plants_list.append({
            "code": code,
            "upi": upi,
            "availability": availability
        })

    return {
        "provider_date": target_day,
        "provider_timezone": "UTC",
        "region_code": raw_pollen_data.get("regionCode"),
        "types": types_list,
        "plants": plants_list
    }

# 他のから呼ばれるやつ
def get_pollen_info(latitude, longitude, target_day):

    raw_pollen_data = get_pollen_data(latitude, longitude)

    if raw_pollen_data != None:

        result = format_pollen_data(raw_pollen_data, target_day)

        return result
    else:
        return None

# テスト用
if __name__ == "__main__":
    output = get_pollen_data(-33.8688, 151.2093)
    print("テスト結果")
    if output:
        pretty_json = json.dumps(output, indent=2, ensure_ascii=False)
        print(pretty_json)

        first_day_date = output["dailyInfo"][0]["date"]
        target_date = f"{first_day_date['year']}-{first_day_date['month']:02d}-{first_day_date['day']:02d}"

        formated = format_pollen_data(output, target_date)
        formated_json = json.dumps(formated, indent=2, ensure_ascii=False)
        print(formated_json)
    else:
        print("\n取得失敗")