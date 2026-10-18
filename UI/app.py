import sys
from pathlib import Path
import streamlit as st
from datetime import date, timedelta

# 1つ上のフォルダー（リポジトリのルート）を読み込み先に追加する（common を使うため）
sys.path.append(str(Path(__file__).resolve().parent.parent))

# 通信制御へMQTTで検索を依頼する関数と、選べる地域の一覧
from mqtt_client import ask_server
from common.locations import LOCATIONS

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
st.sidebar.header("⚙️ ユーザー設定")
selected_allergies = st.sidebar.multiselect(
    "該当するアレルギーを選択",
    ["スギ", "ヒノキ", "ブタクサ", "シラカバ", "カモガヤ", "未登録 / わからない"],
    default=["スギ"]
)

st.sidebar.markdown("---")
location = st.sidebar.selectbox("地域", list(LOCATIONS.keys()), index=0)

today = date.today()
date_options = {
    f"今日 ({today.strftime('%m/%d')})": today,
    f"明日 ({(today + timedelta(days=1)).strftime('%m/%d')})": today + timedelta(days=1),
    f"明後日 ({(today + timedelta(days=2)).strftime('%m/%d')})": today + timedelta(days=2),
}
selected_date_label = st.sidebar.selectbox("確認したい日程", list(date_options.keys()), index=0)


# 検索ボタン。押したときだけMQTTで問い合わせる
# （チェックボックスを触るたびに再検索しないよう、結果は session_state に保存する）
if st.sidebar.button("🔍 対策を調べる", use_container_width=True):
    target_date = date_options[selected_date_label].isoformat()  # 例: "2026-10-20"
    with st.spinner("気象・花粉の情報を取得しています..."):
        st.session_state["result"] = ask_server(location, target_date, selected_allergies)
    st.session_state["searched"] = f"{location} / {selected_date_label}"

if "result" not in st.session_state:
    st.info("サイドバーで地域と日程を選び、「対策を調べる」を押してください。")
    st.stop()

result = st.session_state["result"]

# 失敗したときは、理由を表示してここで終わる
if result["status"] != "success":
    for error in result.get("errors", []):
        st.error(f"取得できませんでした（{error['source']}）: {error['message']}")
    st.stop()

data = result["data"]

if result.get("pollen_is_mock"):
    st.warning("花粉データはダミーの値です（GOOGLE_POLLEN_API_KEY が未設定）。")


# --- メイン画面表示 ---

# 1. 外出設定情報
st.markdown(f"""
<div class="nature-card">
    <div class="section-title">📍 確認中の対象エリア・日程</div>
    <p style="font-size: 1.05rem; color: #4a5d4e; margin: 0;">
        <b>地域・日程:</b> {st.session_state["searched"]}
    </p>
</div>
""", unsafe_allow_html=True)


# 2. 日付ごとの花粉警戒度（高野さんのデータ: data["level"] を表示）
st.markdown(f"""
<div class="warning-card">
    <div class="section-title" style="color: #c85a32;">🚨 {selected_date_label} の花粉警戒度</div>
    <h2 style="color: #e07a5f; margin: 5px 0; font-weight: bold;">【 {data['level']} 】</h2>
</div>
""", unsafe_allow_html=True)

if "未登録 / わからない" not in selected_allergies and len(selected_allergies) > 0:
    allergies_text = "・".join(selected_allergies)
    st.warning(f"🌱 **【アレルギー個別に注意】** {selected_date_label} は **{allergies_text}** の飛散が多くなる見込みです。しっかり対策してお出かけください。")


# 3. 詳細データ（高野さんのデータ: pollen, weather, wind を表示）
st.markdown("<div class='section-title'>📊 予報詳細データ</div>", unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="🌸 予想飛散量", value=data["Pollen"])
with col2:
    st.metric(label="☀️ 天気予報", value=data["weather"])
with col3:
    st.metric(label="💨 予想風速", value=data["Wind"])

st.markdown("<br>", unsafe_allow_html=True)


# 4. おすすめの対策
st.markdown("""
<div class="nature-card">
    <div class="section-title">💡 おでかけ前の対策チェック</div>
</div>
""", unsafe_allow_html=True)

# 推薦プログラムが決めた持ち物・行動を、チェック項目として表示する
for item in data["items"]:
    st.checkbox(item)

st.markdown("<br>", unsafe_allow_html=True)


# 5. 推薦理由（高野さんのデータ: data["reason"] を表示）
st.markdown(f"""
<div class="nature-card">
    <div class="section-title">📝 からだケアのアドバイス</div>
    <p style="color: #526355; line-height: 1.7; margin: 0;">
        {data['reason']}。<br>
        帰宅時は玄関前で衣服の花粉を払い、手洗い・うがい・洗顔で目や鼻についた花粉を優しく洗い流しましょう。
    </p>
</div>
""", unsafe_allow_html=True)

st.caption("花粉対策ナビ - Natural Style UI v2.7 (関数連携対応版)")