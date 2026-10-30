"""recommend.py / llm_advisor.py の仕様確認テスト。
実行: python -m pytest -q test_recommend.py
"""
import json
from types import SimpleNamespace

import pytest

from llm_advisor import make_advisor, make_gemini_advisor, parse_items
from recommend import UserProfile, recommend

SAMPLE = {
    "request_id": "req-001",
    "location": "千葉県習志野市",
    "day": "2026-10-12",
    "Pollen": "多い（雑草花粉）",
    "weather": "おおむね晴れ〜一部曇り",
    "Wind": "最大5.1 m/s",
}
RULE_ITEMS = [
    "マスクを着用する",
    "花粉対策用メガネを持参する",
    "帰宅後は衣服についた花粉を払う",
]
AI_ITEMS = [
    "マスクを着用する",
    "花粉対策用メガネを持参する",
    "帰宅後は衣服の花粉を払う",
]


def test_protocol_fields_match_specification():
    res = recommend(SAMPLE)
    assert res["status"] == "success"
    assert res["errors"] == []
    data = res["data"]
    assert set(data) == {"location", "day", "level", "Pollen", "weather", "Wind", "items", "reason"}
    assert data["day"] == "2026-10-12"
    assert data["Pollen"] == SAMPLE["Pollen"]
    assert data["Wind"] == SAMPLE["Wind"]
    assert isinstance(data["items"], list)
    assert isinstance(data["reason"], str)


def test_legacy_date_pollen_wind_aliases_are_accepted():
    old = {
        "location": "東京",
        "date": "2026-10-12",
        "pollen": "多い",
        "weather": "晴れ",
        "wind": "5.0 m/s",
    }
    res = recommend(old)
    assert res["status"] == "success"
    assert res["data"]["day"] == old["date"]


def test_without_advisor_uses_rule_based_items():
    assert recommend(SAMPLE)["data"]["items"] == RULE_ITEMS


def test_ai_can_change_items_but_not_level():
    res = recommend(SAMPLE, advisor=lambda ctx: AI_ITEMS)
    assert res["status"] == "success"
    assert res["data"]["items"] == AI_ITEMS
    assert res["data"]["level"] == "高"


def test_minimal_context_does_not_include_location_or_user_id():
    seen = {}
    def advisor(ctx):
        seen.update(ctx)
        return AI_ITEMS
    req = dict(SAMPLE, user={"user_id": "secret-uid", "allergies": ["ブタクサ", "謎の花"]})
    recommend(req, advisor=advisor)
    sent = json.dumps(seen, ensure_ascii=False)
    assert seen["level"] == "非常に高い"
    assert seen["matched_allergies"] == ["ブタクサ"]
    assert seen["base_items"][0] == "マスクを着用する"
    assert "習志野" not in sent
    assert "secret-uid" not in sent
    assert "req-001" not in sent


def test_user_profile_argument_is_supported():
    seen = {}
    recommend(SAMPLE, user=UserProfile("u1", ["ブタクサ"]), advisor=lambda c: seen.update(c) or AI_ITEMS)
    assert seen["matched_allergies"] == ["ブタクサ"]


def _boom(ctx):
    raise TimeoutError("timeout")


@pytest.mark.parametrize("advisor", [
    _boom,
    lambda c: [],
    lambda c: "マスクをする",
    lambda c: [1, 2],
    lambda c: ["花粉症の薬を飲む"],
    lambda c: ["診断を受ける"],
    lambda c: ["あ" * 61],
    lambda c: [f"対策{i}" for i in range(7)],
])
def test_bad_ai_result_falls_back_to_rules(advisor):
    res = recommend(SAMPLE, advisor=advisor)
    assert res["status"] == "success"
    assert res["data"]["items"] == RULE_ITEMS
    assert res["errors"] == []


def test_input_error_does_not_call_ai():
    called = []
    res = recommend({"request_id": "x"}, advisor=lambda c: called.append(c) or AI_ITEMS)
    assert res["status"] == "error"
    assert called == []
    assert res["data"] is None
    assert res["errors"]
    assert res["errors"][0]["source"] == "location"


def test_ai_items_are_deduplicated():
    res = recommend(SAMPLE, advisor=lambda c: ["マスクを着用する", "マスクを着用する", " 帰宅後は洗顔する "])
    assert res["data"]["items"] == ["マスクを着用する", "帰宅後は洗顔する"]


def test_parse_items_plain_json_and_code_fence():
    assert parse_items('{"items": ["a", "b"]}') == ["a", "b"]
    assert parse_items('```json\n{"items": ["a"]}\n```') == ["a"]


@pytest.mark.parametrize("text", ["ごめんなさい", "{not json}", '{"foo": 1}', '{"items": "a"}'])
def test_parse_items_rejects_bad_text(text):
    with pytest.raises((ValueError, json.JSONDecodeError)):
        parse_items(text)


class FakeGeminiClient:
    def __init__(self, text):
        self.calls = []
        self._text = text
        self.models = SimpleNamespace(generate_content=self._generate_content)

    def _generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self._text)


def test_gemini_advisor_request_response_and_schema():
    client = FakeGeminiClient(json.dumps({"items": AI_ITEMS}, ensure_ascii=False))
    res = recommend(SAMPLE, advisor=make_gemini_advisor(client=client, model="gemini-test"))
    assert res["data"]["items"] == AI_ITEMS
    call = client.calls[0]
    assert call["model"] == "gemini-test"
    assert call["config"]["response_mime_type"] == "application/json"
    assert "level" in call["config"]["system_instruction"]
    sent = json.loads(call["contents"])
    assert sent["level"] == "高"
    assert sent["base_items"] == RULE_ITEMS


def test_gemini_advisor_caches_same_context():
    client = FakeGeminiClient(json.dumps({"items": AI_ITEMS}, ensure_ascii=False))
    advisor = make_gemini_advisor(client=client)
    recommend(SAMPLE, advisor=advisor)
    recommend(SAMPLE, advisor=advisor)
    assert len(client.calls) == 1


def test_gemini_non_json_reply_falls_back_to_rules():
    client = FakeGeminiClient("申し訳ありません")
    res = recommend(SAMPLE, advisor=make_gemini_advisor(client=client))
    assert res["data"]["items"] == RULE_ITEMS


def test_make_advisor_remains_provider_agnostic():
    advisor = make_advisor(lambda system, user: '{"items": ["マスクを着用する"]}')
    assert recommend(SAMPLE, advisor=advisor)["data"]["items"] == ["マスクを着用する"]


@pytest.mark.parametrize(("code", "expected"), [(0, "clear"), (3, "other"), (61, "rain"), (71, "rain"), (95, "rain")])
def test_open_meteo_weather_code(code, expected):
    from recommend import normalize_weather
    assert normalize_weather(code) == expected


def test_numeric_open_meteo_weather_code_is_displayed_in_japanese():
    req = dict(SAMPLE, weather=0)
    res = recommend(req)
    assert res["data"]["weather"] == "晴れ"
