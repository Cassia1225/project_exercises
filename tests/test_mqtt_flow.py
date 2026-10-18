"""MQTTでやり取りするデータの作り方を確認するテスト。

実際のAPIやMQTTブローカーには接続しない。
実行方法（リポジトリのルートで）: python -m pytest -q tests
"""
from common.locations import find_location
from get_weather_data import pick_day
from get_pollen_data import format_pollen_data
from send_recommend import make_recommend_input
from server import make_worker_request, make_recommend_request
from recommend import recommend


# ---------- 地域（通信制御） ----------

def fake_search(address):
    """国土地理院の住所検索のかわり（テストではネットに接続しない）"""
    return (35.68166, 140.027267)


def test_prefectures_and_cities_are_listed():
    from common.locations import PREFECTURES, cities_of
    assert len(PREFECTURES) == 47
    assert PREFECTURES[0] == "北海道"
    assert "習志野市" in cities_of("千葉県")


def test_find_location_returns_coordinates():
    place = find_location("千葉県 習志野市", search=fake_search)
    assert place["name"] == "千葉県 習志野市"
    assert place["latitude"] == 35.68166
    assert place["longitude"] == 140.027267


def test_find_location_unknown_returns_none():
    # 一覧にない地域は、住所検索を呼ばずに None
    called = []
    assert find_location("千葉県 どこでもない町", search=lambda a: called.append(a)) is None
    assert find_location("習志野市", search=lambda a: called.append(a)) is None
    assert called == []


# ---------- 気象 ----------

def test_pick_day_chooses_the_requested_date():
    daily = {
        "time": ["2026-10-19", "2026-10-20"],
        "weather_code": [61, 0],
        "wind_speed_10m_max": [8.0, 3.2],
        "temperature_2m_mean": [15.0, 18.5],
        "relative_humidity_2m_mean": [90, 55],
    }
    result = pick_day(daily, "2026-10-20")
    assert result == {
        "weather_code": 0,
        "wind_speed_max": 3.2,
        "temperature_mean": 18.5,
        "humidity_mean": 55,
    }


def test_pick_day_returns_none_when_date_missing():
    daily = {
        "time": ["2026-10-19"],
        "weather_code": [0],
        "wind_speed_10m_max": [1.0],
        "temperature_2m_mean": [20.0],
        "relative_humidity_2m_mean": [50],
    }
    assert pick_day(daily, "2026-10-25") is None


# ---------- 花粉 ----------

GOOGLE_SAMPLE = {
    "dailyInfo": [
        {
            "date": {"year": 2026, "month": 10, "day": 19},
            "pollenTypeInfo": [
                {"code": "GRASS", "indexInfo": {"value": 1}},
            ],
        },
        {
            "date": {"year": 2026, "month": 10, "day": 20},
            "pollenTypeInfo": [
                {"code": "GRASS", "indexInfo": {"value": 2}},
                {"code": "TREE"},  # indexInfo がない＝値なし
                {"code": "WEED", "indexInfo": {"value": 4}},
            ],
        },
    ]
}


def test_format_pollen_data_uses_max_upi_of_the_date():
    result = format_pollen_data(GOOGLE_SAMPLE, "2026-10-20")
    assert result["upi"] == 4
    assert result["types"] == {"GRASS": 2, "TREE": None, "WEED": 4}


def test_format_pollen_data_without_the_date_has_no_upi():
    result = format_pollen_data(GOOGLE_SAMPLE, "2026-10-23")
    assert result["upi"] is None


# ---------- 通信制御が作るメッセージ ----------

UI_REQUEST = {
    "request_id": "test-001",
    "location": "千葉県 習志野市",
    "date": "2026-10-20",
    "allergies": ["スギ"],
}


def test_make_worker_request_has_place_and_date():
    place = find_location("千葉県 習志野市", search=fake_search)
    message = make_worker_request(UI_REQUEST, place)
    assert message["request_id"] == "test-001"
    assert message["date"] == "2026-10-20"
    assert message["latitude"] == place["latitude"]
    assert "allergies" not in message  # 気象・花粉にはアレルギーを送らない


def test_make_recommend_request_combines_both_results():
    weather_result = {"request_id": "test-001", "status": "success",
                      "data": {"weather_code": 0, "wind_speed_max": 3.2}}
    pollen_result = {"request_id": "test-001", "status": "success",
                     "data": {"upi": 4, "types": {"WEED": 4}}, "is_mock": False}
    message = make_recommend_request(UI_REQUEST, weather_result, pollen_result)
    assert message["weather"]["weather_code"] == 0
    assert message["pollen"]["upi"] == 4
    assert message["allergies"] == ["スギ"]


# ---------- 推薦（既存の recommend() へ渡す形） ----------

def test_recommend_input_works_with_existing_recommend_function():
    message = {
        "request_id": "test-001",
        "location": "千葉県 習志野市",
        "date": "2026-10-20",
        "allergies": [],
        "weather": {"weather_code": 0, "wind_speed_max": 3.2},
        "pollen": {"upi": 4, "types": {"WEED": 4}},
    }
    response = recommend(make_recommend_input(message))
    assert response["status"] == "success"
    assert response["data"]["level"] == "高"
    assert response["data"]["weather"] == "晴れ"


def test_recommend_input_with_missing_pollen_becomes_error():
    message = {
        "request_id": "test-002",
        "location": "千葉県 習志野市",
        "date": "2026-10-20",
        "allergies": [],
        "weather": {"weather_code": 0, "wind_speed_max": 3.2},
        "pollen": None,  # 花粉の取得に失敗した
    }
    response = recommend(make_recommend_input(message))
    assert response["status"] == "error"


# ---------- 壊れた・おかしなメッセージへの備え ----------

class FakeMessage:
    def __init__(self, text):
        self.payload = text.encode("utf-8")


def test_read_json_ignores_non_dict():
    from common import mqtt_settings as ms
    assert ms.read_json(FakeMessage("[1, 2]")) is None
    assert ms.read_json(FakeMessage("{broken")) is None
    assert ms.read_json(FakeMessage('{"a": 1}')) == {"a": 1}


def test_server_ignores_unknown_source():
    import server
    server.waiting["x1"] = {"ui_request": UI_REQUEST, "weather": None, "pollen": None}
    server.on_worker_result(None, {"request_id": "x1", "source": "ui_request"})
    assert server.waiting["x1"]["ui_request"] == UI_REQUEST
    server.waiting.clear()


# ---------- 花粉の指数が出ていない日（シーズン外など） ----------

def test_format_pollen_data_marks_date_found_even_without_index():
    raw = {"dailyInfo": [{"date": {"year": 2026, "month": 10, "day": 20},
                          "pollenTypeInfo": [{"code": "TREE"}, {"code": "GRASS"}]}]}
    result = format_pollen_data(raw, "2026-10-20")
    assert result["upi"] is None
    assert result["types"] == {"TREE": None, "GRASS": None}


def test_pollen_worker_returns_success_when_index_is_missing(monkeypatch):
    import send_pollen
    monkeypatch.setattr(send_pollen, "get_pollen_info",
                        lambda lat, lon, d: ({"upi": None, "types": {"TREE": None}}, False))
    reply = send_pollen.handle_request({"request_id": "p1", "latitude": 35, "longitude": 140, "date": "2026-10-20"})
    assert reply["status"] == "success"
    assert reply["data"]["upi"] is None


def test_recommend_without_pollen_index_shows_level_unknown():
    from send_recommend import make_response
    message = {
        "request_id": "test-003",
        "location": "千葉県 習志野市",
        "date": "2026-10-20",
        "allergies": [],
        "weather": {"weather_code": 0, "wind_speed_max": 3.2},
        "pollen": {"upi": None, "types": {"TREE": None, "GRASS": None}},
    }
    response = make_response(message)
    assert response["status"] == "partial"
    assert response["data"]["level"] == "判定不可"
    assert response["data"]["weather"] == "晴れ"
    assert response["data"]["Wind"] == "3.2 m/s"


def test_google_days_counts_from_utc_date():
    from datetime import date
    from get_pollen_data import days_needed
    # 日本の10/19 0時台は、UTCではまだ10/18。Googleの1日目は10/18になる
    assert days_needed("2026-10-19", utc_today=date(2026, 10, 18)) == 2
    assert days_needed("2026-10-18", utc_today=date(2026, 10, 18)) == 1
    assert days_needed("2026-10-30", utc_today=date(2026, 10, 18)) == 5
