"""地域解決・気象/花粉取得・推薦を、検索ごとに直接呼び出す。"""
from datetime import date
import logging
import uuid

from common.locations import find_location
from weather.get_weather_data import get_weather
from pollen.get_pollen_data import get_pollen_info
from recommend.service import make_response

logger = logging.getLogger(__name__)


def _error(request_id, code, message, source="server"):
    return {
        "request_id": request_id, "status": "error", "data": None,
        "errors": [{"source": source, "code": code, "message": message}],
    }


def ask_server(location, target_date, allergies):
    """画面の検索条件を受け取り、表示用の結果を返す。共有の待機状態は持たない。"""
    request_id = uuid.uuid4().hex
    if (not isinstance(location, str) or not location.strip()
            or not isinstance(target_date, str)
            or not isinstance(allergies, list)
            or any(not isinstance(value, str) for value in allergies)):
        return _error(request_id, "INVALID_INPUT", "地域・日付・アレルギーの指定を確認してください")
    try:
        if date.fromisoformat(target_date).isoformat() != target_date:
            raise ValueError
    except ValueError:
        return _error(request_id, "INVALID_INPUT", "日付は実在する日をYYYY-MM-DD形式で指定してください")

    try:
        place = find_location(location.strip())
    except ValueError as error:
        return _error(request_id, "INVALID_INPUT", str(error))
    except Exception as error:
        logger.warning("地域の座標を取得できませんでした: %s", type(error).__name__)
        return _error(request_id, "LOCATION_ERROR", "地域の座標を調べられませんでした。もう一度お試しください")
    if place is None:
        return _error(request_id, "LOCATION_NOT_FOUND", "指定した地域が見つかりませんでした")

    errors = []
    weather = None
    try:
        weather = get_weather(place["latitude"], place["longitude"], target_date)
    except Exception as error:
        logger.warning("気象情報を取得できませんでした: %s", type(error).__name__)
    if weather is None:
        errors.append({"source": "weather", "code": "API_ERROR", "message": "気象情報を取得できませんでした"})

    pollen = None
    is_mock = False
    try:
        pollen, is_mock = get_pollen_info(place["latitude"], place["longitude"], target_date)
    except Exception as error:
        logger.warning("花粉情報を取得できませんでした: %s", type(error).__name__)
    if pollen is None or not pollen.get("types"):
        pollen = None
        errors.append({"source": "pollen", "code": "API_ERROR", "message": "花粉情報を取得できませんでした"})

    try:
        result = make_response({
            "request_id": request_id, "location": place["name"], "date": target_date,
            "allergies": list(allergies), "weather": weather, "pollen": pollen,
        })
    except Exception as error:
        logger.warning("推薦を作成できませんでした: %s", type(error).__name__)
        result = _error(request_id, "PROCESSING_ERROR", "対策を作成できませんでした", "recommend")
    result["pollen_is_mock"] = is_mock
    result["errors"] = errors + result.get("errors", [])
    return result
