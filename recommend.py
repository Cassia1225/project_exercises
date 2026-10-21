"""花粉対策の推薦ロジック

入力例（データ収集側から渡される dict）:
    {
        "request_id": "req-001",
        "location": "千葉県習志野市",
        "day": "2026-10-12",  # date でも可
        "Pollen": "多い（雑草花粉）",  # pollen でも可
        "weather": "おおむね晴れ〜一部曇り",  # Open-Meteo weather_code の数値でも可
        "Wind": "最大5.1 m/s",  # wind でも可。共通仕様の単位は m/s
        "pollen_types": ["weed"],
        "user": {"allergies": ["スギ"]}
    }

成功時の data:
    location, date, level, Pollen, weather, Wind, items, reason

使い方:
    from recommend import recommend 紛らわしい。
    response = recommend(request_dict)  # ルールベースのみ。外部通信なし

    from llm_advisor import make_gemini_advisor
    advisor = make_gemini_advisor()  # GEMINI_API_KEY 環境変数を使用
    response = recommend(request_dict, advisor=advisor)

役割分担:
    level（対策レベル）
    items（対策文）… Geminiが利用できる場合は生成。失敗時はルールベースに戻す
"""
import json
import logging
import re

logger = logging.getLogger(__name__)

# 生成AIに渡す関数の型: 文脈 dict を受け取り、対策文のリストを返す（失敗時は例外）
# （advisor という名前で recommend() に渡す。渡さなければ生成AIは使わない）

SCHEMA_VERSION = "1.0"

POLLEN_NUMERIC_SCALE = "count"
# 風速の閾値 (m/s): 未満=calm / 未満=moderate / 以上=strong
WIND_CALM_MAX = 3.0
WIND_STRONG_MIN = 7.0

LEVELS = ["低", "中", "高", "非常に高い"]  # level の表記（UIと要合意）

_POLLEN_JP = {"low": "少ない", "medium": "やや多い", "high": "多い", "very_high": "非常に多い"}
_POLLEN_BASE_SCORE = {"low": 0, "medium": 1, "high": 2, "very_high": 3}

# アレルギー名・花粉種の表記ゆれを吸収する表（小文字で比較する）
_ALIASES = {
    "sugi": ["sugi", "スギ", "すぎ", "杉", "japanese_cedar", "japanese cedar"],
    "hinoki": ["hinoki", "ヒノキ", "ひのき", "檜", "japanese_cypress", "japanese cypress"],
    "ragweed": ["ragweed", "ブタクサ", "ぶたくさ"],
    "mugwort": ["mugwort", "ヨモギ", "よもぎ", "蓬"],
    "tree": ["tree", "樹木", "木本"],
    "grass": ["grass", "イネ科", "graminales"],
    "weed": ["weed", "雑草"],
}
# 個別の花粉種 → 大分類
_GROUP = {"sugi": "tree", "hinoki": "tree", "ragweed": "weed", "mugwort": "weed"}
_JP_NAME = {
    "sugi": "スギ", "hinoki": "ヒノキ", "ragweed": "ブタクサ", "mugwort": "ヨモギ",
    "tree": "樹木", "grass": "イネ科", "weed": "雑草",
}

# 生成AIの出力を受け入れる条件（MVP方針: 薬品・診断には踏み込まない、法律的に問題がある）
MAX_ITEMS = 6
MAX_ITEM_LEN = 60
_FORBIDDEN_WORDS = ("薬", "服用", "処方", "診断", "治療", "病院", "サプリ")


class UserProfile:
    """利用者の情報（ID と アレルギーの一覧）をまとめておく入れ物。"""

    def __init__(self, user_id="", allergies=None):
        self.user_id = user_id
        if allergies is None:
            allergies = []
        self.allergies = allergies  # 例: ["sugi", "スギ", "ブタクサ"]


class InputError(Exception):
    """入力が使えないときの例外。プロトコルの errors 1件に対応する。"""

    def __init__(self, source, code, message):
        super().__init__(message)
        self.source = source
        self.code = code
        self.message = message

    def to_dict(self):
        return {"source": self.source, "code": self.code, "message": self.message}



# 正規化部分
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

# 長い語を先に判定する（「非常に多い」「やや多い」を「多い」より前に）
_POLLEN_WORDS = [
    ("非常に多い", "very_high"), ("極めて多い", "very_high"),
    ("very_high", "very_high"), ("very high", "very_high"),
    ("やや多い", "medium"), ("中程度", "medium"), ("普通", "medium"), ("medium", "medium"),
    ("多い", "high"), ("high", "high"),
    ("少ない", "low"), ("ほとんどない", "low"), ("なし", "low"), ("low", "low"),
]
_POLLEN_SHORT = {"l": "low", "m": "medium", "med": "medium", "h": "high", "vh": "very_high"}


def _is_number_like(raw):
    """数値、または "12" "3.5" のような数字だけの文字列なら True。"""
    if isinstance(raw, bool):
        return False
    if isinstance(raw, (int, float)):
        return True
    if not isinstance(raw, str):
        return False
    if re.fullmatch(r"\s*-?\d+(?:\.\d+)?\s*", raw) is None:
        return False
    return True


def _contains_any(text, words):
    """text の中に、words のどれか1つでも含まれていれば True。"""
    for word in words:
        if word in text:
            return True
    return False


def _remove_duplicates(values):
    """リストから重複を取り除く（最初に出てきた順番は保つ）。"""
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _number_text(value):
    """数値を表示用の文字にする。5.0 のような整数は "5" にする。"""
    number = float(value)
    if number == int(number):
        return str(int(number))
    return str(number)


def _pollen_from_number(v):
    if v < 0:
        raise InputError("pollen", "INVALID_VALUE", f"花粉量が負の値です: {v}")
    if POLLEN_NUMERIC_SCALE == "upi":  # 0〜5段階
        if v <= 1:
            return "low"
        if v <= 3:
            return "medium"
        if v <= 4:
            return "high"
        return "very_high"
    if v < 20:
        return "low"
    if v < 50:
        return "medium"
    if v < 80:
        return "high"
    return "very_high"


def normalize_pollen(raw):
    """花粉量を 'low' / 'medium' / 'high' / 'very_high' に正規化する。
    解釈できない値は黙って medium にせず InputError を投げる。"""
    if _is_number_like(raw):
        return _pollen_from_number(float(raw))
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s in _POLLEN_SHORT:
            return _POLLEN_SHORT[s]
        for word, cat in _POLLEN_WORDS:
            if word in s:
                return cat
    raise InputError("pollen", "INVALID_VALUE", f"花粉量を解釈できません: {raw!r}")


def _wind_category(v):
    if v < WIND_CALM_MAX:
        return "calm"
    if v < WIND_STRONG_MIN:
        return "moderate"
    return "strong"


def normalize_wind(raw):
    """風速を 'calm' / 'moderate' / 'strong' に正規化する。
    "最大5.1 m/s" や "30 km/h"、"強い" のような文字列も受け付ける。"""
    if _is_number_like(raw):
        return _wind_category(float(raw))
    if isinstance(raw, str):
        s = raw.strip().lower()
        # 文字の中の数字を全部取り出す（例: "3〜5 m/s" → [3.0, 5.0]）
        numbers = []
        for n in _NUMBER_RE.findall(s):
            numbers.append(float(n))
        if len(numbers) > 0:
            v = max(numbers)  # "3〜5 m/s" のような幅は大きい方を採用
            if "km/h" in s or "km／h" in s or "キロ" in s:
                v /= 3.6
            return _wind_category(v)
        if "やや強い" in s or s in ("moderate", "普通"):
            return "moderate"
        if "強い" in s or s == "strong":
            return "strong"
        if "弱い" in s or "穏やか" in s or s in ("calm", "weak"):
            return "calm"
    raise InputError("wind", "INVALID_VALUE", f"風速を解釈できません: {raw!r}")


def normalize_weather(raw):
    """天気を 'rain' / 'clear' / 'other' に正規化する。

    Open-Meteo の WMO weather_code（例: 0, 61, 71, 95）にも対応する。
    花粉対策では、雨・雪・にわか雨を rain として扱う。
    """
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        code = int(raw)
        if code == 0:
            return "clear"
        if code in (1, 2):
            return "clear"
        if code in (3, 45, 48):
            return "other"
        if 51 <= code <= 67 or 80 <= code <= 82 or 95 <= code <= 99:
            return "rain"
        if 71 <= code <= 77 or code in (85, 86):
            return "rain"
        return "other"

    s = str(raw).strip().lower()
    if re.fullmatch(r"\d+", s):
        return normalize_weather(int(s))
    if _contains_any(s, ("雨", "雪", "rain", "shower", "snow", "drizzle", "thunderstorm")):
        return "rain"
    if _contains_any(s, ("晴", "clear", "sunny")):
        return "clear"
    return "other"


def _canon_allergen(name):
    """表記ゆれのある名前（例: "杉"）を、決まった名前（例: "sugi"）に直す。表になければ None。"""
    n = name.strip().lower()
    for key, aliases in _ALIASES.items():
        for alias in aliases:
            if n == alias.lower():
                return key
    return None


def _extract_pollen_types(pollen_raw, explicit):
    """当日の花粉種を、pollen_types と pollen の文字列（例:「多い（雑草花粉）」）から集める。"""
    types = set()
    if explicit is None:
        explicit = []
    for t in explicit:
        c = _canon_allergen(str(t))
        if c:
            types.add(c)
    if isinstance(pollen_raw, str):
        text = pollen_raw.lower()
        for key, aliases in _ALIASES.items():
            for alias in aliases:
                if alias.lower() in text:
                    types.add(key)
                    break
    return types


def _allergy_matches(allergies, types):
    """登録アレルギーのうち、当日の花粉種と一致するもの（大分類も考慮）を返す。"""
    matched = []
    for a in allergies:
        c = _canon_allergen(str(a))
        if c is None:
            c = str(a).strip().lower()
        for t in types:
            # 同じ種類か、片方がもう片方の大分類（例: sugi と tree）なら一致とみなす
            if c == t or _GROUP.get(c) == t or _GROUP.get(t) == c:
                matched.append(str(a))
                break
    return matched



# 推薦の部分（レベル判定と対策リストいるかわからん）

def evaluate(pollen_cat, wind_cat, weather_cat, matched_allergies=None):
    """正規化済みの値から level / items / reasons を決める。"""
    score = _POLLEN_BASE_SCORE[pollen_cat]
    reasons = [f"花粉の飛散量が「{_POLLEN_JP[pollen_cat]}」"]

    if wind_cat == "strong":
        score += 1
        reasons.append("風が強く、花粉が拡散しやすい")
    if weather_cat == "clear":
        reasons.append("晴れの時間帯があり、花粉が飛散しやすい")
    elif weather_cat == "rain":
        reasons.append("雨で空中の花粉は減る可能性があるが、衣服に付着しやすい")
    if matched_allergies:
        score += 1
        reasons.append(f"登録アレルギー（{'、'.join(matched_allergies)}）の飛散が見込まれる")

    # score を 0〜3（LEVELS の番号）の範囲におさめる
    idx = score
    if idx < 0:
        idx = 0
    if idx > len(LEVELS) - 1:
        idx = len(LEVELS) - 1

    items = []
    if idx >= 2:
        items += ["マスクを着用する", "花粉対策用メガネを持参する", "帰宅後は衣服についた花粉を払う"]
        if idx == 3:
            items += ["帰宅後は洗顔・うがいをする", "外出は必要な範囲にとどめる"]
    elif idx == 1:
        items += ["マスクを着用する", "帰宅後は手洗い・うがいをする"]
    else:
        items += ["窓の開け閉めは短時間にする"]
    if idx >= 1 and wind_cat == "strong":
        items.append("風の強い時間帯の長時間の外出を避ける")
    if idx >= 1 and weather_cat == "rain":
        items.append("濡れた衣服は早めに着替える")

    return {"level": LEVELS[idx], "items": _remove_duplicates(items), "reasons": reasons}



# 生成AIとの連携部分（送るデータの組み立て、対策文の検証）

def _clip(value, limit=60):
    """外部から来た文字列を1行・短くして、生成AIに渡せる形にする。"""
    return re.sub(r"\s+", " ", str(value)).strip()[:limit]


def build_llm_context(level, pollen_text, wind_text, weather_text, time_text, matched_allergies, base_items):
    """生成AIに送るデータ。必要最小限にする（user_id・地域名・生の入力は送らない）。
    level は Python が決めた確定値で、AIには変更させない。"""
    matched_jp = []
    for name in matched_allergies:
        key = _canon_allergen(name)
        if key:  # 表にない自由記述は送らない
            matched_jp.append(_JP_NAME[key])

    if time_text:
        time_value = _clip(time_text)
    else:
        time_value = None

    return {
        "level": level,
        "pollen": _clip(pollen_text),
        "wind": _clip(wind_text),
        "weather": _clip(weather_text),
        "time": time_value,
        "matched_allergies": matched_jp,
        "base_items": base_items,
    }


def clean_items(items):
    """生成AIが返した対策文を検証する。使えなければ ValueError。
    （AIの出力はそのままUIに出さず、必ずここを通す）"""
    if not isinstance(items, list) or not items:
        raise ValueError("items が空、またはリストではありません")
    cleaned = []
    for it in items:
        if not isinstance(it, str):
            raise ValueError("items に文字列以外が含まれています")
        text = it.strip()
        if not text:
            continue
        if len(text) > MAX_ITEM_LEN:
            raise ValueError(f"対策文が長すぎます（{len(text)}文字）")
        if _contains_any(text, _FORBIDDEN_WORDS):
            raise ValueError(f"MVP方針外の語を含みます: {text}")
        cleaned.append(text)
    cleaned = _remove_duplicates(cleaned)
    if not cleaned or len(cleaned) > MAX_ITEMS:
        raise ValueError(f"対策文の件数が不正です（{len(cleaned)}件）")
    return cleaned



# プロトコル（JSON）への組み立て

def _error_response(request_id, errors):
    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "status": "error",
        "data": None,
        "errors": errors,
    }


def _upstream_errors(request):
    """データ収集側がエラーを返してきた場合、その内容を取り出す。"""
    errors = request.get("errors")
    if not errors:
        errors = []
    if request.get("status") == "error" and not errors:
        errors = [{"source": "unknown", "code": "UPSTREAM_ERROR", "message": "上流の処理でエラーが発生しました"}]

    result = []
    for e in errors:
        if not isinstance(e, dict):
            continue  # 辞書でないものは読み飛ばす
        result.append({
            "source": str(e.get("source", "unknown")),
            "code": str(e.get("code", "UPSTREAM_ERROR")),
            "message": str(e.get("message", "上流の処理でエラーが発生しました")),
        })
    return result


def _is_empty(value):
    """None や、空白だけの文字列なら True。"""
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _require_any(payload, keys, label):
    """仕様書のキーと旧実装の小文字キーの両方を受け付ける。"""
    for key in keys:
        value = payload.get(key)
        if not _is_empty(value):
            return value
    raise InputError(keys[0], "MISSING_DATA", f"{label}がありません")


def _display(raw, fallback):
    """UIに返す表示用の文字列。文字列ならそのまま、数値なら fallback を使う。"""
    if isinstance(raw, str) and not _is_number_like(raw):
        return raw
    return fallback


def _weather_display(raw, category):
    """Open-Meteo の weather_code が数値なら、UI向けの日本語に変換する。"""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        code = int(raw)
    elif isinstance(raw, str) and re.fullmatch(r"\s*\d+\s*", raw):
        code = int(raw.strip())
    else:
        return str(raw)

    if code == 0:
        return "晴れ"
    if code in (1, 2):
        return "おおむね晴れ・一部くもり"
    if code == 3:
        return "くもり"
    if code in (45, 48):
        return "霧"
    if 51 <= code <= 67 or 80 <= code <= 82:
        return "雨・にわか雨"
    if 71 <= code <= 77 or code in (85, 86):
        return "雪"
    if 95 <= code <= 99:
        return "雷雨"
    if category == "clear":
        return "晴れ"
    if category == "rain":
        return "雨・雪など"
    return "くもりなど"


def recommend(request, user=None, include_reasons=False, advisor=None):
    """推薦のメイン関数。例外は投げず、必ずプロトコルの dict を返す。

    advisor（生成AIに文脈を送って対策文を返す関数）を渡すと、items をAIが作る。
    advisor が失敗したり、返答が検証を通らなかった場合は、ルールベースの items に戻す。
    advisor=None なら外部通信は一切しない。
    """
    if not isinstance(request, dict):
        return _error_response(None, [{"source": "request", "code": "INVALID_INPUT", "message": "入力が dict ではありません"}])

    request_id = request.get("request_id")

    # 上流（データ収集側）のエラーはそのまま返す
    upstream = _upstream_errors(request)
    if upstream:
        return _error_response(request_id, upstream)

    # {"status": "success", "data": {...}} の封筒形式にも対応
    if isinstance(request.get("data"), dict):
        payload = request["data"]
    else:
        payload = request

    try:
        _require_any(payload, ["location"], "対象の地域名")
        _require_any(payload, ["day", "date"], "外出予定の日付")
        pollen_raw = _require_any(payload, ["Pollen", "pollen"], "花粉情報")
        weather_raw = _require_any(payload, ["weather"], "気象情報（天気）")
        wind_raw = _require_any(payload, ["Wind", "wind"], "気象情報（風速）")

        pollen_cat = normalize_pollen(pollen_raw)
        wind_cat = normalize_wind(wind_raw)
        weather_cat = normalize_weather(weather_raw)
    except InputError as e:
        return _error_response(request_id, [e.to_dict()])

    # ユーザー情報（引数が優先。なければ request["user"]）
    allergies = []
    if user is not None:
        allergies = list(user.allergies)
    elif isinstance(payload.get("user"), dict):
        user_allergies = payload["user"].get("allergies")
        if user_allergies:
            allergies = list(user_allergies)

    types = _extract_pollen_types(pollen_raw, payload.get("pollen_types"))
    if allergies:
        matched = _allergy_matches(allergies, types)
    else:
        matched = []

    result = evaluate(pollen_cat, wind_cat, weather_cat, matched)

    # 風速が数値なら "5.1 m/s" の形にする
    if _is_number_like(wind_raw):
        wind_fallback = _number_text(wind_raw) + " m/s"
    else:
        wind_fallback = str(wind_raw)
    wind_text = _display(wind_raw, wind_fallback)
    pollen_text = _display(pollen_raw, _POLLEN_JP[pollen_cat])

    # 日付は "day" か "date" のどちらかに入っている
    day = payload.get("day")
    if not day:
        day = payload.get("date")

    # 対策文: 既定はルールベース。advisor があれば生成AIに作らせる（失敗時はルールベースに戻す）
    items = result["items"]
    if advisor is not None:
        context = build_llm_context(
            result["level"], pollen_text, wind_text, str(weather_raw),
            day, matched, items,
        )
        try:
            items = clean_items(advisor(context))
        except Exception as e:  # 通信失敗・タイムアウト・不正な返答など、すべて同じ扱い
            logger.warning("生成AIの対策文を使えなかったため、ルールベースの対策を返します: %s", e)
            items = result["items"]

    # UIとの共通仕様：location / date / level / Pollen / weather / Wind / items / reason
    # 入力の「day」は共通仕様の「date」に統一して返す。
    data = {
        "location": payload.get("location"),
        "day": day,
        "level": result["level"],
        "Pollen": pollen_text,
        "weather": _weather_display(weather_raw, weather_cat),
        "Wind": wind_text,
        "items": items,
        "reason": "。".join(result["reasons"]),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "status": "success",
        "data": data,
        "errors": [],
    }



# サンプル実行: python recommend.py

if __name__ == "__main__":
    from llm_advisor import make_gemini_advisor

    sample = {
        "request_id": "req-001",
        "location": "千葉県習志野市",
        "day": "2026-10-12",
        "Pollen": "多い（雑草花粉）",
        "weather": "おおむね晴れ〜一部曇り",
        "Wind": "最大5.1 m/s",
    }

    try:
        # Gemini APIを使用するための関数を作成
        advisor = make_gemini_advisor()

        # Geminiを使って対策文を生成
       
        result = recommend(sample, advisor=advisor)

        print(json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        ))

    except Exception as e:
        print("Gemini APIの準備に失敗しました")
        print(type(e).__name__, str(e))