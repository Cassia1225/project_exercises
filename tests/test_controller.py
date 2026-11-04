"""地域・API取得・推薦を直接つなぐ経路を、外部通信だけ置換して検証する。"""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from server import server as controller


@pytest.fixture
def services(monkeypatch):
    calls = []
    def weather(lat, lon, date):
        calls.append(("weather", lat, lon, date))
        return {"weather_code": 0, "wind_speed_max": 1.0}
    def pollen(lat, lon, date):
        calls.append(("pollen", lat, lon, date))
        return {"upi": 3, "types": {"WEED": 3}}, False
    monkeypatch.setattr(controller, "find_location", lambda name: {
        "name": "確定した地域", "latitude": 35.0, "longitude": 140.0,
    })
    monkeypatch.setattr(controller, "get_weather", weather, raising=False)
    monkeypatch.setattr(controller, "get_pollen_info", pollen, raising=False)
    return SimpleNamespace(calls=calls)


def test_search_returns_recommendation_with_resolved_location_and_date(services):
    result = controller.ask_server("入力地域", "2026-11-04", [])
    assert result["status"] == "success"
    assert result["request_id"]
    assert result["data"]["location"] == "確定した地域"
    assert result["data"]["date"] == "2026-11-04"
    assert "day" not in result["data"]
    assert result["data"]["level"] == "中"
    assert result["pollen_is_mock"] is False
    assert services.calls == [("weather", 35.0, 140.0, "2026-11-04"),
                              ("pollen", 35.0, 140.0, "2026-11-04")]


def test_missing_pollen_index_keeps_weather_and_partial_status(services, monkeypatch):
    monkeypatch.setattr(controller, "get_pollen_info", lambda *args: (
        {"upi": None, "types": {"TREE": None}}, False,
    ), raising=False)
    result = controller.ask_server("入力地域", "2026-11-04", [])
    assert result["status"] == "partial"
    assert result["data"]["level"] == "判定不可"
    assert result["data"]["weather"] == "晴れ"


@pytest.mark.parametrize("service,source", [("get_weather", "weather"), ("get_pollen_info", "pollen")])
def test_failed_api_becomes_visible_error_without_fabricated_data(services, monkeypatch, service, source):
    def fail(*args):
        raise ConnectionError("test-only unavailable service")
    monkeypatch.setattr(controller, service, fail, raising=False)
    result = controller.ask_server("入力地域", "2026-11-04", [])
    assert result["status"] == "error"
    assert result["data"] is None
    assert any(error["source"] == source for error in result["errors"])
    assert result["pollen_is_mock"] is False


def test_missing_api_key_still_marks_dummy_pollen(services, monkeypatch):
    from pollen import get_pollen_data
    monkeypatch.setattr(get_pollen_data, "API_KEY", "")
    monkeypatch.setattr(controller, "get_pollen_info", get_pollen_data.get_pollen_info, raising=False)
    result = controller.ask_server("入力地域", "2026-11-04", [])
    assert result["status"] == "success"
    assert result["pollen_is_mock"] is True


@pytest.mark.parametrize("problem,code", [(None, "LOCATION_NOT_FOUND"),
                                        (ValueError("候補が複数あります"), "INVALID_INPUT"),
                                        (ConnectionError("unavailable"), "LOCATION_ERROR")])
def test_location_failure_does_not_call_forecast_apis(services, monkeypatch, problem, code):
    def location(name):
        if isinstance(problem, Exception):
            raise problem
        return problem
    monkeypatch.setattr(controller, "find_location", location)
    result = controller.ask_server("入力地域", "2026-11-04", [])
    assert result["status"] == "error"
    assert result["errors"][0]["code"] == code
    assert services.calls == []


@pytest.mark.parametrize("location,date,allergies", [
    ("", "2026-11-04", []), (None, "2026-11-04", []),
    ("地域", "not-a-date", []), ("地域", "2026-02-30", []),
    ("地域", "2026-11-04", "スギ"), ("地域", "2026-11-04", [123]),
])
def test_invalid_input_returns_error_without_api_calls(services, location, date, allergies):
    result = controller.ask_server(location, date, allergies)
    assert result["status"] == "error"
    assert result["errors"][0]["code"] == "INVALID_INPUT"
    assert services.calls == []


def test_simultaneous_searches_do_not_mix_request_ids_or_locations(services, monkeypatch):
    monkeypatch.setattr(controller, "find_location", lambda name: {
        "name": name, "latitude": 35.0, "longitude": 140.0,
    })
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda name: controller.ask_server(name, "2026-11-04", []), ["地域A", "地域B"]))
    assert [result["data"]["location"] for result in results] == ["地域A", "地域B"]
    assert results[0]["request_id"] != results[1]["request_id"]
