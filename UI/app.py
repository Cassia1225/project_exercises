"""元の画面構成を使い、ボタンを押したときだけ予報を取得する。"""

from datetime import datetime, timedelta
from html import escape
from pathlib import Path
import os
import sys

# プロジェクトのルートから共通ファイルを読み込む。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import requests
import streamlit as st
from dotenv import load_dotenv
from common.protocol import SCHEMA, JST, ALLERGENS
from UI.browser import browser_bridge
from UI.state import consume_event

load_dotenv()
BASE = os.getenv("CONTROLLER_URL", "http://127.0.0.1:8000").rstrip("/")


def call_api(method, path, payload):
    """通信制御プログラムへ送り、受け取ったJSONを返す。"""
    try:
        if method == "get":
            response = requests.get(BASE + path, params=payload, timeout=55)
        else:
            response = requests.post(BASE + path, json=payload, timeout=55)
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("応答がJSONのオブジェクトではありません。")
        if response.status_code >= 400:
            for error in data.get("errors", []):
                st.error(error.get("message", "処理できませんでした。"))
            return None
        return data
    except (requests.RequestException, ValueError):
        st.error(
            "通信制御プログラムに接続できません。一括起動した端末を確認してください。"
        )
        return None


# --- ページ基本設定 ---
st.set_page_config(
    page_title="花粉対策ナビ",
    page_icon="🌿",
    layout="centered"
)

# --- カスタムCSS ---
st.markdown("""
<style>
    .stApp { background-color: #faf8f5; font-family: 'Helvetica Neue', Arial, 'Hiragino Kaku Gothic ProN', sans-serif; }
    .nature-card { background-color: #ffffff; padding: 22px; border-radius: 16px; box-shadow: 0 4px 12px rgba(120, 140, 120, 0.08); margin-bottom: 20px; border: 1px solid #e2ebd8; }
    .warning-card { background-color: #fffaf5; padding: 22px; border-radius: 16px; box-shadow: 0 4px 12px rgba(220, 120, 100, 0.08); margin-bottom: 20px; border-left: 6px solid #e07a5f; border-top: 1px solid #f2e3d5; border-right: 1px solid #f2e3d5; border-bottom: 1px solid #f2e3d5; }
    .main-title { color: #2d4a3e; font-weight: 700; text-align: center; margin-bottom: 25px; letter-spacing: 1px; }
    .section-title { color: #3d5a45; font-size: 1.15rem; font-weight: bold; margin-bottom: 12px; display: flex; align-items: center; }
    [data-testid="stSidebar"] { background-color: #f0f4ed; }
</style>
""", unsafe_allow_html=True)

# --- ヘッダー ---
st.markdown("<h1 class='main-title'>🌿 花粉対策ナビ</h1>", unsafe_allow_html=True)

# --- サイドバー ---
state = st.session_state
state.setdefault("allergies", [])
state.setdefault("browser_ready", False)
state.setdefault("chosen_location", None)

with st.sidebar:
    st.header("⚙️ ユーザー設定")
    # 入力欄の表示位置を先に確保し、保存設定は入力欄を作る前に読み込む。
    settings_area = st.container()
    with st.expander("現在地・保存設定"):
        allergy_state = "unknown"
        if state["allergies"]:
            allergy_state = "selected"
        profile = {
            "allergy_state": allergy_state,
            "allergies": state["allergies"],
        }
        event = browser_bridge(profile, state["browser_ready"], state.get("browser_ack"))
        new_event = consume_event(state, event)
        if new_event:
            if new_event["kind"] == "geo":
                coordinates = {
                    "latitude": new_event.get("latitude"),
                    "longitude": new_event.get("longitude"),
                }
                with st.spinner("現在いる市区町村を確認しています…"):
                    answer = call_api("post", "/api/v1/locations/current", coordinates)
                if answer:
                    state["chosen_location"] = answer["location"]
                    state["prefecture"] = answer["location"]["prefecture"]
                    state["previous_prefecture"] = answer["location"]["prefecture"]
                    state["municipality_candidate"] = answer["location"]["candidate_id"]
                    state["browser_message"] = "現在地：" + answer["location"]["name"]
                    state["gps_accuracy"] = new_event.get("accuracy_m")
                else:
                    state["browser_message"] = "現在地の市区町村を特定できませんでした。都道府県と市区町村を選択してください。"
            st.rerun()
        if state.get("browser_message"):
            st.caption(state["browser_message"])
        if state.get("gps_accuracy") is not None:
            st.caption(f"位置取得の精度（目安）：約{state['gps_accuracy']:.0f}m。市区町村名を確認してください。")
        if not state["browser_ready"]:
            if st.checkbox("保存設定を使わずに続ける", key="skip_storage"):
                state["browser_ready"] = True
                st.rerun()

    with settings_area:
        selected_allergies = st.multiselect(
            "該当するアレルギーを選択",
            list(ALLERGENS),
            format_func=ALLERGENS.get,
            key="allergies",
            placeholder="未登録 / わからない",
            help="任意の設定です。未設定を「アレルギーなし」とは扱いません。同じブラウザーへ保存します。",
        )
        st.markdown("---")
        # 地域の一覧だけを一度読み込む。選択操作では予報を取得しない。
        if "location_options" not in state:
            with st.spinner("都道府県・市区町村を読み込んでいます…"):
                answer = call_api("get", "/api/v1/locations/options", {})
            state["location_options"] = []
            if answer is not None:
                state["location_options"] = answer.get("candidates", [])
        location_options = state["location_options"]
        if not location_options:
            st.info("地域一覧を取得できませんでした。通信状態と起動した端末を確認してください。")
            if st.button("地域一覧を再読み込み", key="reload_locations"):
                state.pop("location_options")
                st.rerun()

        # 一覧は自治体コード順。重複を除いて、都道府県の選択肢を作る。
        prefectures = []
        for municipality in location_options:
            name = municipality["prefecture"]
            if name not in prefectures:
                prefectures.append(name)
        if state.get("prefecture") not in prefectures:
            state["prefecture"] = None
        prefecture = st.selectbox(
            "都道府県",
            prefectures,
            index=None,
            placeholder="都道府県を選択",
            key="prefecture",
            disabled=not prefectures,
        )

        # 別の都道府県へ変えたら、以前の市区町村を引き継がない。
        if prefecture != state.get("previous_prefecture"):
            state["municipality_candidate"] = None
            state["chosen_location"] = None
            state.pop("gps_accuracy", None)
            state["previous_prefecture"] = prefecture
        municipalities = {}
        for municipality in location_options:
            if municipality["prefecture"] == prefecture:
                municipalities[municipality["candidate_id"]] = municipality
        names = {}
        for candidate_id, municipality in municipalities.items():
            names[candidate_id] = municipality["name"].removeprefix(prefecture)
        if state.get("municipality_candidate") not in names:
            state["municipality_candidate"] = None
        candidate_id = st.selectbox(
            "市区町村",
            list(names),
            index=None,
            placeholder="市区町村を選択",
            format_func=names.get,
            key="municipality_candidate",
            disabled=not names,
        )
        chosen = municipalities.get(candidate_id)
        previous_location = state["chosen_location"]
        if previous_location:
            if chosen is None or chosen["candidate_id"] != previous_location["candidate_id"]:
                state.pop("gps_accuracy", None)
        state["chosen_location"] = chosen

        today = datetime.now(JST).date()
        tomorrow = today + timedelta(days=1)
        day_after_tomorrow = today + timedelta(days=2)
        date_options = {
            f"今日 ({today.strftime('%m/%d')})": today,
            f"明日 ({tomorrow.strftime('%m/%d')})": tomorrow,
            f"明後日 ({day_after_tomorrow.strftime('%m/%d')})": day_after_tomorrow,
        }
        selected_date_label = st.selectbox("確認したい日程", list(date_options), key="target_date")
        target = date_options[selected_date_label]
        if st.button(
            "花粉・気象と対策を取得", key="get_forecast", type="primary",
            disabled=not chosen or not state["browser_ready"],
        ):
            allergy_state = "unknown"
            if selected_allergies:
                allergy_state = "selected"
            query = {
                "schema_version": SCHEMA,
                "location_input": {
                    "mode": "search",
                    "candidate_id": chosen["candidate_id"],
                },
                "date": target.isoformat(),
                "allergy_state": allergy_state,
                "allergies": list(selected_allergies),
            }
            with st.spinner("気象・花粉を取得しています…"):
                state["result"] = call_api("post", "/api/v1/recommendations", query)
    if os.getenv("APP_MODE") == "demo":
        st.caption("デモモード：気象・花粉は架空データです。地域一覧の読み込みには通信が必要です。")


# --- メイン画面表示 ---
result = state.get("result") or {}
result_data = result.get("data")
meta = result.get("meta") or {}
details = result.get("details") or {}

# 初回も元のカードを表示する。取得前の値を予報として見せない。
location_text = "地域を選択してください"
if prefecture:
    location_text = prefecture
if chosen:
    location_text = chosen["name"]
display_date = selected_date_label
level = "未取得"
pollen_text = "未取得"
weather_text = "未取得"
wind_text = "未取得"
advice = "地域と日程を選び、「花粉・気象と対策を取得」を押してください。"
if result_data:
    # 入力を変えただけでは、以前の結果の地域・日付を書き換えない。
    location_text = result_data["location"]
    display_date = result_data["date"]
    for label, day in date_options.items():
        if day.isoformat() == result_data["date"]:
            display_date = label
    level = result_data.get("level") or "判定不可"
    # 元の大きな文字を保つため、数値の根拠は詳細に、要約は短く表示する。
    pollen_labels = {
        "低": "少ない",
        "中": "やや多い",
        "高": "多い",
        "非常に高い": "非常に多い",
    }
    pollen_text = pollen_labels.get(level, "未取得")
    weather_text = result_data.get("weather", "未取得")
    wind_text = result_data.get("wind", "未取得").removeprefix("日最大 ")
    items = result_data.get("items") or []
    if items:
        advice = "。".join(items) + "。"
    else:
        advice = "取得情報が不足しているため、対策を作れませんでした。"

location = escape(str(location_text))
selected_date_text = escape(str(display_date))

# 1. 外出設定情報
st.markdown(f"""
<div class="nature-card">
    <div class="section-title">📍 確認中の対象エリア・日程</div>
    <p style="font-size: 1.05rem; color: #4a5d4e; margin: 0;">
        <b>地域:</b> {location} &nbsp;|&nbsp; <b>日程:</b> {selected_date_text}
    </p>
</div>
""", unsafe_allow_html=True)

# 2. 日付ごとの花粉警戒度
st.markdown(f"""
<div class="warning-card">
    <div class="section-title" style="color: #c85a32;">🚨 {selected_date_text} の花粉警戒度</div>
    <h2 style="color: #e07a5f; margin: 5px 0; font-weight: bold;">【 {escape(level)} 】</h2>
</div>
""", unsafe_allow_html=True)

# 取得状態を明示する。アレルギーを選んだだけで「飛散が多い」とは表示しない。
if meta.get("is_mock"):
    st.warning("デモ結果：気象・花粉の値は架空データです。")
if meta.get("is_provisional"):
    st.warning("暫定結果：取得できた設定種だけで判定しています。")
elif result.get("status") == "partial":
    st.warning("一部の情報が不足しています。取得できた情報を表示します。")
if meta.get("assessed_allergies") and level in ("高", "非常に高い"):
    st.warning(f"🌱 **【アレルギー個別に注意】** {display_date} の設定した花粉の対策レベルは **{level}** です。")

# 3. 詳細データ
st.markdown("<div class='section-title'>📊 予報詳細データ</div>", unsafe_allow_html=True)
col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="🌸 予想飛散量", value=pollen_text)
with col2:
    st.metric(label="☀️ 天気予報", value=weather_text)
with col3:
    st.metric(label="💨 予想風速", value=wind_text)
st.markdown("<br>", unsafe_allow_html=True)

# 4. おすすめの対策（元の4つのチェック項目）
st.markdown("""
<div class="nature-card">
    <div class="section-title">💡 おでかけ前の対策チェック</div>
</div>
""", unsafe_allow_html=True)
st.checkbox("😷 花粉ガードマスクを着用した", key="countermeasure_0")
st.checkbox("👓 メガネ・サングラスを着用した", key="countermeasure_1")
st.checkbox("🧥 つるつるした素材の上着を選んだ", key="countermeasure_2")
st.checkbox("🧹 帰宅時に花粉を払う準備（ブラシ等）", key="countermeasure_3")
st.markdown("<br>", unsafe_allow_html=True)

# 5. 推薦された対策を、元のアドバイス欄に表示する。
st.markdown(f"""
<div class="nature-card">
    <div class="section-title">📝 からだケアのアドバイス</div>
    <p style="color: #526355; line-height: 1.7; margin: 0;">
        {escape(advice)}<br>
        帰宅時は玄関前で衣服の花粉を払い、手洗い・うがい・洗顔で目や鼻についた花粉を優しく洗い流しましょう。
    </p>
</div>
""", unsafe_allow_html=True)

# 新しい仕様で必要な詳細は、元のカード配置を保って折りたたむ。
if result:
    st.caption("対策文は授業の実演用案です。班で内容を確認する前のものです。")
    with st.expander("種類別の花粉情報・取得状況"):
        if result_data:
            st.write("判定の根拠：" + result_data.get("pollen", "未取得"))
            st.write("判定理由：" + result_data.get("reason", ""))
            if meta.get("personalization_status") == "general":
                st.caption("未設定のため、地域分類の花粉指数による一般情報です。")
            else:
                st.caption("設定した花粉のうち、取得できた種類から判定しています。")
        selected = meta.get("assessed_allergies", []) + meta.get("unavailable_allergies", [])
        pollen = details.get("pollen") or {}
        entries = (pollen.get("types") or []) + (pollen.get("plants") or [])
        selected_rows = []
        other_rows = []
        status_labels = {
            "available": "取得済み",
            "missing": "未取得",
            "unsupported": "対応外",
            "unknown": "対応未確認",
        }
        for entry in entries:
            upi = "未取得"
            if entry.get("upi") is not None:
                upi = str(entry["upi"])
            row = {
                "種類": entry.get("name", entry.get("code")),
                "UPI": upi,
                "取得状況": status_labels.get(entry.get("availability"), "未確認"),
            }
            if entry.get("code") in selected:
                selected_rows.append(row)
            else:
                other_rows.append(row)
        if selected_rows:
            st.write("**設定した種類**")
            st.dataframe(selected_rows, hide_index=True, width="stretch")
        if other_rows:
            st.write("**地域・その他の種類**")
            st.dataframe(other_rows, hide_index=True, width="stretch")
        reference = details.get("regional_reference")
        if selected and reference:
            st.caption(f"地域の参考レベル：{reference['level']}（分類の最大UPI {reference['upi']}）。個人向け判定とは別です。")
        for message in (result.get("errors") or []) + (result.get("warnings") or []):
            st.warning(message.get("message", "情報が不足しています。"))
        st.caption("気象は日本時間の日別値、花粉はUTCの日付です。同じ24時間の予報ではありません。")
        st.caption("取得完了（UTC）：" + str(meta.get("fetched_at") or "未取得"))
        st.caption("出典：気象 Open-Meteo ／ 花粉 Google Maps ／ 市区町村 国土地理院")
    if details.get("pollen") and not meta.get("is_mock"):
        st.markdown('<p style="font:400 14px sans-serif;color:#5e5e5e"><span translate="no" style="white-space:nowrap">Google Maps</span><br>Source: Includes pollen data from Google</p>', unsafe_allow_html=True)
        st.caption("Includes data from Google Maps（花粉指数に基づくレベル・対策）")

st.caption("花粉対策ナビ - Natural Style UI v2.7 (関数連携対応版)")
