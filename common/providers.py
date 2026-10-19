"""外部APIの取得補助と、実データと区別したデモ用データ。"""

from datetime import datetime, timezone
import requests
from .protocol import ProtocolError, deadline


class ProviderError(ProtocolError):
    pass


def fetch_json(
    url, *, session=requests, params=None, headers=None, timeout=8, source="api"
):
    try:
        r = session.get(url, params=params, headers=headers or {}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError, TypeError):
        # 例外文にはAPIキーなどが含まれる場合があるため、そのまま表示しない。
        raise ProviderError(
            "API_ERROR", "外部サービスから情報を取得できませんでした。", source
        ) from None


def request_timeout(request):
    remaining = (
        deadline(request.get("expires_at")) - datetime.now(timezone.utc)
    ).total_seconds()
    if remaining <= 0:
        raise ProviderError("EXPIRED", "取得要求の期限が切れました。")
    return min(8, remaining)


def mock_data(source, request):
    if source == "weather":
        return {
            "provider_date": request["date"],
            "timezone": "Asia/Tokyo",
            "weather_code": 0,
            "wind_speed_max": 3.5,
            "temperature_mean": 20.0,
            "humidity_mean": 60,
            "units": {
                "wind_speed_max": "m/s",
                "temperature_mean": "°C",
                "humidity_mean": "%",
            },
        }

    def make_entry(code, provider, name, upi):
        return {
            "code": code,
            "provider_code": provider,
            "name": name,
            "upi": upi,
            "availability": "available",
        }

    return {
        "provider_date": request["date"],
        "provider_timezone": "UTC",
        "region_code": "JP",
        "types": [
            make_entry("tree", "TREE", "樹木", 4),
            make_entry("grass", "GRASS", "イネ科", 1),
        ],
        "plants": [
            make_entry("sugi", "JAPANESE_CEDAR", "スギ", 4),
            make_entry("hinoki", "JAPANESE_CYPRESS", "ヒノキ", 1),
        ],
        "_warnings": [
            {
                "source": "pollen",
                "code": "MOCK_DATA",
                "message": "花粉の指数・種類は動作確認用の架空値です。",
            }
        ],
    }
