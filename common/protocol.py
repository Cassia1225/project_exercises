"""通信で使う項目・値を確認する。取得担当への要求にはキーや個人設定を含めない。"""

from datetime import date, datetime, timedelta, timezone
import math
import re
import time
from uuid import UUID

SCHEMA = "1.2-draft"
JST = timezone(timedelta(hours=9))
ALLERGENS = {
    "sugi": "スギ",
    "hinoki": "ヒノキ",
    "grass": "イネ科",
    "ragweed": "ブタクサ",
    "birch": "シラカバ",
    "kamogaya": "カモガヤ",
}
TOPIC_ROOT = "project_exercises/v1"


class ProtocolError(ValueError):
    def __init__(self, code, message, source="request"):
        super().__init__(message)
        self.code = code
        self.message = message
        self.source = source

    def as_dict(self):
        return {
            "source": self.source,
            "code": self.code,
            "message": self.message,
        }


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def number(value, low=-math.inf, high=math.inf):
    return (
        type(value) in (int, float)
        and low <= value <= high
        and (type(value) is int or math.isfinite(value))
    )


def valid_upi(value):
    return type(value) is int and 0 <= value <= 5


def coordinates(lat, lon):
    if not number(lat, 20, 46) or not number(lon, 122, 154):
        raise ProtocolError("OUTSIDE_JAPAN", "日本国内の市区町村を指定してください。")


def valid_date(value):
    try:
        d = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ProtocolError(
            "INVALID_DATE", "対象日はYYYY-MM-DD形式で指定してください。"
        ) from None
    today = datetime.now(JST).date()
    if value != d.isoformat() or not today <= d <= today + timedelta(days=2):
        raise ProtocolError(
            "INVALID_DATE", "対象日は日本時間の今日から明後日までです。"
        )
    return value


def settings(value):
    if not isinstance(value, dict):
        raise ProtocolError("INVALID_SETTINGS", "アレルギー設定の形式が不正です。")
    state = value.get("allergy_state")
    allergies = value.get("allergies")
    if (
        state not in ("selected", "unknown")
        or not isinstance(allergies, list)
        or any(not isinstance(a, str) or a not in ALLERGENS for a in allergies)
        or len(allergies) != len(set(allergies))
        or len(allergies) > len(ALLERGENS)
        or (state == "unknown" and allergies)
        or (state == "selected" and not allergies)
    ):
        raise ProtocolError(
            "INVALID_SETTINGS", "未設定、または一覧にある花粉の種類を指定してください。"
        )
    return {
        "allergy_state": state,
        "allergies": list(allergies),
    }


def base(payload):
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA:
        raise ProtocolError(
            "INVALID_SCHEMA",
            "通信の版が一致しません。アプリを同じ版で起動してください。",
        )


def validate_query(payload):
    base(payload)
    valid_date(payload.get("date"))
    settings(payload)
    loc = payload.get("location_input")
    if not isinstance(loc, dict):
        raise ProtocolError("INVALID_LOCATION", "市区町村を選択してください。")
    if loc.get("mode") == "search":
        if not isinstance(loc.get("candidate_id"), str) or not re.fullmatch(
            r"gsi:\d{5}", loc["candidate_id"]
        ):
            raise ProtocolError(
                "INVALID_LOCATION", "候補から市区町村を選択してください。"
            )
    elif loc.get("mode") == "current":
        coordinates(loc.get("latitude"), loc.get("longitude"))
    else:
        raise ProtocolError("INVALID_LOCATION", "地域の指定方法が不正です。")
    return payload


def deadline(value):
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if d.tzinfo is None:
            raise ValueError
        return d
    except (AttributeError, TypeError, ValueError):
        raise ProtocolError("INVALID_DEADLINE", "要求期限の形式が不正です。") from None


def validate_worker_request(payload):
    base(payload)
    valid_date(payload.get("date"))
    coordinates(payload.get("latitude"), payload.get("longitude"))
    try:
        UUID(payload.get("request_id"))
    except (ValueError, AttributeError, TypeError):
        raise ProtocolError("INVALID_ID", "検索IDが不正です。") from None
    if not isinstance(payload.get("controller_id"), str) or not re.fullmatch(
        r"[a-zA-Z0-9_-]{1,64}", payload["controller_id"]
    ):
        raise ProtocolError("INVALID_ID", "通信制御IDが不正です。")
    if not isinstance(payload.get("location_id"), str) or not re.fullmatch(
        r"gsi:\d{5}", payload["location_id"]
    ):
        raise ProtocolError("INVALID_LOCATION", "位置IDが不正です。")
    remaining = (
        deadline(payload.get("expires_at")) - datetime.now(timezone.utc)
    ).total_seconds()
    if not 0 < remaining <= 60:
        raise ProtocolError("EXPIRED", "要求の期限が切れたか、長すぎます。")
    if type(payload.get("is_mock")) is not bool:
        raise ProtocolError("INVALID_MODE", "データモードが不正です。")
    return payload


def matches_result(reply, request, source):
    if not isinstance(reply, dict) or source not in ("weather", "pollen"):
        return False
    try:
        if deadline(request["expires_at"]) <= datetime.now(timezone.utc):
            return False
    except (ProtocolError, KeyError):
        return False
    # 他の検索・日付・地域の返信を、この検索結果に混ぜない。
    matched_fields = (
        "schema_version",
        "request_id",
        "controller_id",
        "location_id",
        "date",
        "is_mock",
    )
    for key in matched_fields:
        if reply.get(key) != request.get(key):
            return False
    if type(reply.get("is_mock")) is not bool or reply.get("source") != source:
        return False
    if reply.get("status") not in ("success", "error"):
        return False
    if not isinstance(reply.get("errors"), list) or not isinstance(
        reply.get("warnings"), list
    ):
        return False
    if reply["status"] == "success":
        return isinstance(reply.get("data"), dict)
    return reply.get("data") is None


def error_response(request_id, errors, is_mock=False):
    """失敗時も画面が同じ項目を読めるように、共通の形で返す。"""
    # metaは、デモかどうか・判定できたかなど、結果の状態を伝える。
    metadata = {
        "is_mock": is_mock,
        "assessment_scope": "none",
        "personalization_status": "not_evaluated",
        "is_provisional": False,
        "assessed_allergies": [],
        "unavailable_allergies": [],
        "recommendation_source": "none",
        "rule_version": "demo-0.2",
        "fetched_at": None,
        "timezone": "Asia/Tokyo",
        "pollen_timezone": "UTC",
    }
    return {
        "schema_version": SCHEMA,
        "request_id": request_id,
        "status": "error",
        "data": None,
        "details": None,
        "errors": errors,
        "warnings": [],
        "meta": metadata,
    }


def remaining(until, cap, source="controller"):
    seconds = until - time.monotonic()
    if seconds <= 0:
        raise ProtocolError(
            "TIMEOUT", "処理の待機期限を超えました。再検索してください。", source
        )
    return min(cap, seconds)
