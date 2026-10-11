

# 生データ取得
def get_pollen_data(location):
    # 今はダミー
    raw_pollen_data = {
        "region": location,
        "daily_index": 3,
        "status_code": 200
    }

    return raw_pollen_data

# データ成型
def format_pollen_data(raw_pollen_data):

    formated_data = {
        "status": "success",
        "location": raw_pollen_data["region"],
        "pollen_level": raw_pollen_data["daily_index"]
    }

    return formated_data

# 他のから呼ばれるやつ
def get_pollen_info(location):

    raw_pollen_data = get_pollen_data(location)

    result = format_pollen_data(raw_pollen_data)


    return result

# if __name__ == "__main__":
#