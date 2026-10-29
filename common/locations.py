"""国内自治体・海外都市の名前から緯度・経度を調べる処理。

- 一覧（municipalities.json）は、国土地理院の自治体一覧（muni.js）から作ったもの。
- 緯度・経度は、国土地理院の住所検索で「千葉県習志野市」のように調べる。
  （気象APIと花粉APIは、地域名ではなく緯度・経度で指定するため）
"""
import json
from pathlib import Path

import requests

# {"北海道": ["札幌市", "札幌市中央区", ...], "青森県": [...], ...}
with open(Path(__file__).parent / "municipalities.json", encoding="utf-8") as f:
    MUNICIPALITIES = json.load(f)

PREFECTURES = list(MUNICIPALITIES.keys())  # 北海道〜沖縄県の順

OVERSEAS_SEARCH_URL = "https://geocoding-api.open-meteo.com/v1/search"

SEARCH_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch"

# 一度調べた住所の座標を覚えておく（同じ地域を何度も問い合わせないため）
_cache = {}


def cities_of(prefecture):
    """都道府県の市区町村の一覧を返す。"""
    return MUNICIPALITIES.get(prefecture, [])


def search_gsi(address):
    """国土地理院の住所検索で (緯度, 経度) を調べる。見つからなければ None。"""
    if address in _cache:
        return _cache[address]

    res = requests.get(SEARCH_URL, params={"q": address}, timeout=5)
    res.raise_for_status()
    results = res.json()

    point = None
    for feature in results:
        # 住所が完全に一致する結果を使う（よく似た別の地名を使わないため）
        if feature["properties"]["title"] == address:
            longitude, latitude = feature["geometry"]["coordinates"]  # 経度が先なので注意
            point = (latitude, longitude)
            break

    _cache[address] = point
    return point


def search_overseas(name):
    """都市名＋国名・州名から座標を調べる。複数候補は勝手に選ばない。"""
    # API仕様: https://open-meteo.com/en/docs/geocoding-api
    params = {"name": name, "count": 100, "language": "en", "format": "json"}
    # 主要都市のプリセットにある略称を、APIが受け取れる国コードへ直す
    city_name, qualifier = name.rsplit(",", 1)
    country_aliases = {"usa": "US", "uk": "GB"}
    country_code = country_aliases.get(qualifier.strip().lower())
    if country_code:
        params["name"] = city_name.strip()
        params["countryCode"] = country_code
    response = requests.get(
        OVERSEAS_SEARCH_URL,
        params=params,
        timeout=5,
    )
    response.raise_for_status()
    results = response.json().get("results", [])
    if not results:
        return None

    # 前方一致で返る別の都市を除き、入力した都市名と完全一致する候補を優先する
    city_name = name.split(",")[0].strip().casefold()
    exact = []
    for place in results:
        if place["name"].casefold() == city_name:
            exact.append(place)
    if exact:
        results = exact
    if len(results) != 1:
        raise ValueError("都市の候補が複数あります。都市名の後に国名または州名を付けて絞り込んでください。")

    place = results[0]
    label_parts = []
    for key in ["name", "admin1", "country"]:
        value = place.get(key)
        if value and value not in label_parts:
            label_parts.append(value)
    return {
        "name": ", ".join(label_parts),
        "latitude": place["latitude"],
        "longitude": place["longitude"],
    }


def find_location(name, search=search_gsi):
    """ "千葉県 習志野市" から {name, latitude, longitude} を返す。

    国内一覧にない地域や、座標が見つからない場合は None。
    海外は "Paris, France" のようなカンマ区切りで検索する。
    search はテストのときに偽物の関数と入れ替えられるようにしている。
    """
    # 海外UIはカンマ区切り。国内の自治体選択と区別して調べる
    if "," in name:
        return search_overseas(name.strip())

    parts = name.split(" ")
    if len(parts) != 2:
        return None

    prefecture, city = parts
    if city not in cities_of(prefecture):
        return None

    point = search(prefecture + city)
    if point is None:
        return None
    
    #分割代入
    latitude, longitude = point
    return {
        "name": name,
        "latitude": latitude,
        "longitude": longitude,
    }
