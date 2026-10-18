import requests
import json
import config  # APIキー


# 生データ取得
def get_pollen_data(latitude=35.6812, longitude=139.7671):

    url = "https://pollen.googleapis.com/v1/forecast:lookup"

    params = {
        "key": config.API_KEY,
        "location.latitude": latitude,
        "location.longitude": longitude,
        "days": 1,
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
def format_pollen_data(raw_pollen_data):

    formatted_data = {
        "status": "success",
        "pollen_level": raw_pollen_data["daily_index"]
    }

    return formatted_data

# 他のから呼ばれるやつ
def get_pollen_info(latitude=-33.8688, longitude=151.2093):

    raw_pollen_data = get_pollen_data(latitude, longitude)

    result = format_pollen_data(raw_pollen_data)

    return result

# テスト用
if __name__ == "__main__":
    output = get_pollen_data(-33.8688, 151.2093)
    print("テスト結果")
    if output:
        pretty_json = json.dumps(output, indent=2, ensure_ascii=False)
        print(pretty_json)
    else:
        print("\n失敗")