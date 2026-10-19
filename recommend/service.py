"""花粉指数から対策レベルを決め、画面へ返す結果を作る。

レベルはPythonで確定する。将来AIを使う場合も、変更するのは対策文だけ。
対策文は授業の実演用案であり、実データかどうかとは別に扱う。
"""

from common.protocol import (
    ALLERGENS,
    SCHEMA,
    ProtocolError,
    base,
    settings,
    valid_upi,
    number,
    error_response,
    now_iso,
)
from .recommend import clean_items, normalize_weather, _weather_display

LEVELS = ("低", "中", "高", "非常に高い")


def level(upi):
    """UPI 0〜5を、4段階の対策レベルへ変換する。"""
    if upi <= 1:
        return LEVELS[0]
    elif upi <= 3:
        return LEVELS[1]
    elif upi == 4:
        return LEVELS[2]
    else:
        return LEVELS[3]


def usable(entry):
    """取得済みで、有効なUPIがある種類かを確認する。"""
    if not isinstance(entry, dict):
        return False
    if entry.get("availability") != "available":
        return False
    return valid_upi(entry.get("upi"))


def rule_items(lv, weather):
    """確定したレベルと気象情報から、持ち物・行動を選ぶ。"""
    items = []
    if lv in ("高", "非常に高い"):
        items = [
            "マスクを着用する",
            "花粉対策用メガネを持参する",
            "帰宅後は衣服についた花粉を払う",
        ]
    elif lv == "中":
        items = ["マスクを着用する", "帰宅後は手洗いをする"]
    elif lv == "低":
        items = ["窓の開け閉めは短時間にする"]
    if lv == "非常に高い":
        items.append("長時間の外出を控えることを検討する")

    # 風と雨は対策を追加するだけで、花粉のレベルは変えない。
    weather_data = weather or {}
    wind = weather_data.get("wind_speed_max")
    if number(wind, 7, 150):
        items.append("風の強い時間帯の長時間の外出を避ける")
    code = weather_data.get("weather_code")
    if type(code) is int and normalize_weather(code) == "rain":
        items.append("雨具を用意する")

    unique_items = []
    for item in items:
        if item not in unique_items:
            unique_items.append(item)
    return unique_items


def assess(payload, advisor=None):
    # 1. 通信形式と、任意のアレルギー設定を確認する。
    request_id = None
    if isinstance(payload, dict):
        request_id = payload.get("request_id")
    try:
        base(payload)
        profile = settings(payload)
    except ProtocolError as exc:
        return error_response(request_id, [exc.as_dict()])

    weather = payload.get("weather")
    if not isinstance(weather, dict):
        weather = None
    pollen = payload.get("pollen")
    if not isinstance(pollen, dict):
        pollen = None
    is_mock = payload.get("is_mock") is True
    errors = list(payload.get("errors") or [])
    warnings = list(payload.get("warnings") or [])
    if weather is None and pollen is None:
        if not errors:
            errors.append(
                {
                    "source": "controller",
                    "code": "NO_DATA",
                    "message": "気象・花粉の両方を取得できませんでした。",
                }
            )
        return error_response(request_id, errors, is_mock)

    # 2. 地域分類と植物を読み、種類のコードで参照できる辞書を作る。
    pollen_types = []
    plants = []
    if pollen:
        pollen_types = pollen.get("types", [])
        plants = pollen.get("plants", [])
    by_code = {}
    for entry in pollen_types + plants:
        if isinstance(entry, dict):
            by_code[entry.get("code")] = entry

    # 樹木全体（tree）の値を、スギ（sugi）の値として代用しない。
    selected = profile["allergies"]
    assessed = []
    unavailable = []
    for allergy in selected:
        if usable(by_code.get(allergy)):
            assessed.append(allergy)
        else:
            unavailable.append(allergy)

    regional_values = []
    for entry in pollen_types:
        if usable(entry):
            regional_values.append(entry["upi"])
    reference = None
    if regional_values:
        regional_upi = max(regional_values)
        reference = {
            "upi": regional_upi,
            "level": level(regional_upi),
        }

    # 3. 設定があれば取得できた設定種、未設定なら地域分類を使う。
    values = []
    if selected:
        for allergy in assessed:
            values.append(by_code[allergy]["upi"])
    else:
        values = regional_values
    upi = None
    assessment_level = None
    if values:
        upi = max(values)
        assessment_level = level(upi)

    provisional = bool(assessed and unavailable)
    if assessed:
        if provisional:
            personalization_status = "partial"
        else:
            personalization_status = "complete"
    elif selected:
        personalization_status = "unavailable"
    else:
        personalization_status = "general"

    assessment_scope = "none"
    if assessment_level is not None:
        if selected:
            assessment_scope = "personal"
        else:
            assessment_scope = "regional"

    # 4. 取得できなかった情報と、判定に使った情報を説明する。
    if unavailable:
        unavailable_names = []
        for allergy in unavailable:
            unavailable_names.append(ALLERGENS[allergy])
        warnings.append(
            {
                "source": "pollen",
                "code": "ALLERGEN_UNAVAILABLE",
                "message": "判定に含められない設定種：" + "、".join(unavailable_names),
            }
        )
    if weather is None:
        warnings.append(
            {
                "source": "weather",
                "code": "MISSING",
                "message": "気象情報が不足しています。",
            }
        )
    if pollen is None:
        warnings.append(
            {
                "source": "pollen",
                "code": "MISSING",
                "message": "花粉情報が不足しています。",
            }
        )

    reasons = []
    if assessment_level is not None:
        reason_subject = "地域の分類"
        if selected:
            reason_subject = "取得できた設定種"
        reasons.append(reason_subject + f"の最大UPI {upi}から判定")
    else:
        reasons.append("判定に必要な花粉指数がなく、レベルは判定不可")
    if provisional:
        reasons.append("一部の設定種のみを使った暫定結果")

    weather_data = weather or {}
    wind = weather_data.get("wind_speed_max")
    wind_text = "未取得"
    if number(wind, 0, 150):
        wind_text = f"日最大 {wind:g} m/s"
    code = weather_data.get("weather_code")
    weather_text = "未取得"
    if type(code) is int:
        weather_text = _weather_display(code, normalize_weather(code))

    # 5. 基本の対策文を選ぶ。AIの接続先が渡された場合だけ生成を試す。
    items = rule_items(assessment_level, weather)
    recommendation_source = "rule"
    if advisor is not None and assessment_level is not None:
        context = {
            "level": assessment_level,
            "upi": upi,
            "weather_code": code,
            "wind_speed_max": wind,
            "base_items": items,
        }
        try:
            generated_items = advisor(context)
            items = clean_items(generated_items)
            recommendation_source = "gemini"
        except Exception:
            warnings.append(
                {
                    "source": "recommend",
                    "code": "ADVISOR_FALLBACK",
                    "message": "対策文の生成に失敗し、基本対策を表示しています。",
                }
            )

    # デモ表示とAI失敗の注意だけなら、データ不足とは扱わない。
    status = "success"
    if (
        unavailable
        or weather is None
        or pollen is None
        or assessment_level is None
        or errors
    ):
        status = "partial"
    else:
        for warning in warnings:
            if warning.get("code") not in ("MOCK_DATA", "ADVISOR_FALLBACK"):
                status = "partial"
                break

    pollen_text = "判定に必要な指数は未取得"
    if upi is not None:
        pollen_subject = "地域分類"
        if selected:
            pollen_subject = "設定種"
        pollen_text = f"{pollen_subject}の最大UPI {upi}"

    # 6. dataは画面用の要約、detailsは取得した詳しい値、metaは判定の状態。
    location = payload.get("location") or {}
    display_data = {
        "location": location.get("name", "未取得"),
        "date": payload.get("date"),
        "level": assessment_level,
        "pollen": pollen_text,
        "weather": weather_text,
        "wind": wind_text,
        "items": items,
        "reason": "。".join(reasons),
    }
    details = {
        "location": location,
        "weather": weather,
        "pollen": pollen,
        "regional_reference": reference,
    }
    metadata = {
        "is_mock": is_mock,
        "assessment_scope": assessment_scope,
        "personalization_status": personalization_status,
        "is_provisional": provisional,
        "assessed_allergies": assessed,
        "unavailable_allergies": unavailable,
        "recommendation_source": recommendation_source,
        "advice_status": "draft",
        "rule_version": "demo-0.2",
        "fetched_at": payload.get("fetched_at") or now_iso(),
        "timezone": "Asia/Tokyo",
        "pollen_timezone": "UTC",
    }
    return {
        "schema_version": SCHEMA,
        "request_id": request_id,
        "status": status,
        "data": display_data,
        "details": details,
        "errors": errors,
        "warnings": warnings,
        "meta": metadata,
    }
