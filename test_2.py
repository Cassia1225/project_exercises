import json

import pytest

from recommend import InputError, UserProfile, normalize_pollen, normalize_wind, recommend

SAMPLE = {
    "request_id": "req-001",
    "location": "千葉県習志野市",
    "date": "2026-10-12",
    "time": "13:00〜15:00",
    "pollen": "多い（雑草花粉）",
    "weather": "おおむね晴れ〜一部曇り",
    "wind": "最大5.1 m/s",
}


def make(**overrides):
    req = dict(SAMPLE)
    req.update(overrides)
    return req


# --- プロトコルのサンプルJSONを再現できること ---------------------------------
def test_success_matches_protocol_sample():
    assert recommend(SAMPLE) == {
        "schema_version": "1.0",
        "request_id": "req-001",
        "status": "success",
        "data": {
            "location": "千葉県習志野市",
            "date": "2026-10-12",
            "time": "13:00〜15:00",
            "level": "高",
            "pollen": "多い（雑草花粉）",
            "weather": "おおむね晴れ〜一部曇り",
            "wind": "最大5.1 m/s",
            "items": [
                "マスクを着用する",
                "花粉対策用メガネを持参する",
                "帰宅後は衣服についた花粉を払う",
            ],
        },
        "errors": [],
    }


def test_upstream_error_is_passed_through():
    req = {
        "request_id": "req-001",
        "status": "error",
        "errors": [{"source": "weather", "code": "API_ERROR", "message": "気象情報を取得できませんでした"}],
    }
    assert recommend(req) == {
        "schema_version": "1.0",
        "request_id": "req-001",
        "status": "error",
        "data": None,
        "errors": [{"source": "weather", "code": "API_ERROR", "message": "気象情報を取得できませんでした"}],
    }


def test_response_is_json_serializable():
    json.dumps(recommend(SAMPLE), ensure_ascii=False)
    json.dumps(recommend({"request_id": "x"}), ensure_ascii=False)


# --- 欠損・不正値は黙って「普通」にせず、エラーにする ---------------------------
@pytest.mark.parametrize("key", ["pollen", "weather", "wind"])
def test_missing_required_field_returns_error(key):
    req = make()
    del req[key]
    res = recommend(req)
    assert res["status"] == "error"
    assert res["data"] is None
    assert res["errors"][0]["source"] == key
    assert res["errors"][0]["code"] == "MISSING_DATA"


def test_none_and_empty_string_are_missing():
    assert recommend(make(weather=None))["errors"][0]["code"] == "MISSING_DATA"
    assert recommend(make(wind=" "))["errors"][0]["code"] == "MISSING_DATA"


def test_unparsable_pollen_returns_error():
    res = recommend(make(pollen="???"))
    assert res["status"] == "error"
    assert res["errors"][0] == {
        "source": "pollen",
        "code": "INVALID_VALUE",
        "message": "花粉量を解釈できません: '???'",
    }


def test_non_dict_request():
    assert recommend("oops")["status"] == "error"


# --- 正規化 -------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("非常に多い", "very_high"),
        ("やや多い", "medium"),
        ("多い（雑草花粉）", "high"),
        ("少ない", "low"),
        ("65", "high"),  # 数値の文字列（前回指摘した不具合）
        (65, "high"),
        (10, "low"),
        ("VH", "very_high"),
        ("high", "high"),
    ],
)
def test_normalize_pollen(raw, expected):
    assert normalize_pollen(raw) == expected


def test_normalize_pollen_rejects_negative():
    with pytest.raises(InputError):
        normalize_pollen(-1)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("最大5.1 m/s", "moderate"),
        ("2", "calm"),
        ("3〜5 m/s", "moderate"),
        ("30 km/h", "strong"),  # 8.3 m/s
        ("25 km/h", "moderate"),  # 6.9 m/s
        ("強い", "strong"),
        ("やや強い", "moderate"),
        ("弱い", "calm"),
        (7, "strong"),
    ],
)
def test_normalize_wind(raw, expected):
    assert normalize_wind(raw) == expected


# --- ロジック -----------------------------------------------------------------
def test_strong_wind_raises_level_and_adds_item():
    res = recommend(make(wind="最大8 m/s"))
    assert res["data"]["level"] == "非常に高い"
    assert "風の強い時間帯の長時間の外出を避ける" in res["data"]["items"]


def test_rain_adds_clothes_item_without_changing_level():
    res = recommend(make(weather="雨"))
    assert res["data"]["level"] == "高"
    assert "濡れた衣服は早めに着替える" in res["data"]["items"]


def test_low_pollen():
    res = recommend(make(pollen="少ない"))
    assert res["data"]["level"] == "低"
    assert res["data"]["items"] == ["窓の開け閉めは短時間にする"]


def test_numeric_input_gets_display_strings():
    res = recommend(make(pollen=65, wind=5.1))
    assert res["data"]["pollen"] == "多い"
    assert res["data"]["wind"] == "5.1 m/s"


def test_allergy_match_raises_level():
    # 雑草花粉の日に、ブタクサ（雑草の一種）を登録 → 大分類で一致
    res = recommend(make(), user=UserProfile("u1", ["ブタクサ"]))
    assert res["data"]["level"] == "非常に高い"


def test_allergy_mismatch_keeps_level():
    res = recommend(make(), user=UserProfile("u1", ["sugi"]))
    assert res["data"]["level"] == "高"


@pytest.mark.parametrize("name", ["sugi", "スギ", "杉", "Sugi"])
def test_allergy_name_variants(name):
    res = recommend(make(pollen="多い（スギ花粉）"), user=UserProfile("u1", [name]))
    assert res["data"]["level"] == "非常に高い"


def test_user_in_request_and_pollen_types():
    req = make(pollen="多い", pollen_types=["sugi"], user={"allergies": ["スギ"]})
    assert recommend(req)["data"]["level"] == "非常に高い"


def test_envelope_input():
    res = recommend({"request_id": "req-9", "status": "success", "data": dict(SAMPLE)})
    assert res["status"] == "success"
    assert res["request_id"] == "req-9"
    assert res["data"]["level"] == "高"


def test_reasons_are_off_by_default_and_optional():
    assert "reasons" not in recommend(SAMPLE)["data"]
    assert recommend(SAMPLE, include_reasons=True)["data"]["reasons"]