"""ブラウザーに保存した設定を確認し、同じ通知を重複して処理しない。"""

import json
from common.protocol import settings, ProtocolError


def restored_settings(raw):
    try:
        value = raw
        if isinstance(raw, str):
            value = json.loads(raw)
        if (
            not isinstance(value, dict)
            or type(value.get("version")) is not int
            or value["version"] != 1
        ):
            raise ValueError
        return settings(value)
    except (ValueError, TypeError, ProtocolError):
        return {
            "allergy_state": "unknown",
            "allergies": [],
        }


def consume_event(state, event):
    if (
        not isinstance(event, dict)
        or not isinstance(event.get("id"), str)
        or len(event["id"]) > 100
    ):
        return None
    if event["id"] == state.get("browser_ack"):
        return None
    kind = event.get("kind")
    if kind not in ("loaded", "saved", "deleted", "storage_error", "geo", "geo_error"):
        return None
    # 同じ通知で保存や現在地取得を繰り返さないよう、受取済みIDを残す。
    state["browser_ack"] = event["id"]
    if kind == "loaded":
        profile = restored_settings(event.get("profile"))
        state["allergies"] = profile["allergies"]
        state["browser_ready"] = True
        if profile["allergies"]:
            state["browser_message"] = "設定を復元しました。"
        else:
            state["browser_message"] = "アレルギーは未設定です。"
        if event.get("storage_ok") is False:
            state["browser_message"] = (
                "このブラウザーでは設定を保存できません。今回の検索は利用できます。"
            )
    elif kind == "deleted":
        state["allergies"] = []
        state["browser_message"] = "保存したアレルギー設定を削除しました。"
    elif kind == "saved":
        state["browser_message"] = "アレルギー設定をこのブラウザーに保存しました。"
    elif kind == "storage_error":
        state["browser_message"] = "設定を保存できません。今回の検索は利用できます。"
    elif kind == "geo_error":
        state["browser_message"] = str(
            event.get("message", "現在地を取得できませんでした。")
        )[:200]
    return event
