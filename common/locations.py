"""都道府県・市区町村の一覧と、地域名から緯度・経度を調べる処理。

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


def find_location(name, search=search_gsi):
    """ "千葉県 習志野市" から {name, latitude, longitude} を返す。

    一覧にない地域や、座標が見つからない場合は None。
    search はテストのときに偽物の関数と入れ替えられるようにしている。
    """
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
