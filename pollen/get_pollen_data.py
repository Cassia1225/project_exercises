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

    # 花粉対策レベルが最も高い種類の植物の情報のみを抽出
    plants = raw_pollen_data["dailyInfo"][0]["pollenTypeInfo"]
    max_value = -1
    selected = None
    for plant in plants:
        val = plant["indexInfo"].get("value", 0)
        if val > max_value:
            max_value = val
            selected = plant

    index_info = selected.get("indexInfo")
    if index_info:
        formatted_data = {
            "level": index_info.get("category"),
            "pollen": selected.get("displayName"),
            # "recommend": selected.get("healthRecommendations")
        }
    else:
        formatted_data = {
            "level": None,
            "pollen": selected.get("displayName"),
            # "recommend": selected.get("healthRecommendations")
        }

    return formatted_data

# 他のから呼ばれるやつ
def get_pollen_info(latitude, longitude):

    raw_pollen_data = get_pollen_data(latitude, longitude)

    if raw_pollen_data != None:

        result = format_pollen_data(raw_pollen_data)

        return result
    else:
        return None

# テスト用
if __name__ == "__main__":
    output = get_pollen_info(-33.8688, 151.2093)
    print("テスト結果")
    if output:
        pretty_json = json.dumps(output, indent=2, ensure_ascii=False)
        print(pretty_json)
    else:
        print("\n失敗")