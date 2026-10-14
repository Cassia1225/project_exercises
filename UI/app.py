import streamlit as st
from datetime import date, timedelta

# 【追加】高野さんが作ったファイルを読み込む（同じフォルダに recommend.py を置いておく）
try:
    from recommend import get_recommendation
except ImportError:
    # まだ高野さんのファイルがない場合のダミー処理
    def get_recommendation(loc, d, a):
        return {
            "level": "注意レベル：高",
            "pollen": "取得中...",
            "weather": "取得中...",
            "wind": "取得中...",
            "advice": "データ連携の準備中です。"
        }

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
location = st.sidebar.text_input("地域", value="千葉県 習志野市")

today = date.today()
date_options = {
    f"今日 ({today.strftime('%m/%d')})": today,
    f"明日 ({(today + timedelta(days=1)).strftime('%m/%d')})": today + timedelta(days=1),
    f"明後日 ({(today + timedelta(days=2)).strftime('%m/%d')})": today + timedelta(days=2),
}
selected_date_label = st.sidebar.selectbox("確認したい日程", list(date_options.keys()), index=0)


# =========================================================
# 【重要】高野さんの関数を実行してデータを受け取る！
# =========================================================
data = get_recommendation(location, selected_date_label, selected_allergies)


# --- メイン画面表示 ---

# 1. 外出設定情報
st.markdown(f"""
<div class="nature-card">
    <div class="section-title">📍 確認中の対象エリア・日程</div>
    <p style="font-size: 1.05rem; color: #4a5d4e; margin: 0;">
        <b>地域:</b> {location} &nbsp;|&nbsp; <b>日程:</b> {selected_date_label}
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
    st.metric(label="🌸 予想飛散量", value=data["pollen"])
with col2:
    st.metric(label="☀️ 天気予報", value=data["weather"])
with col3:
    st.metric(label="💨 予想風速", value=data["wind"])

st.markdown("<br>", unsafe_allow_html=True)


# 4. おすすめの対策
st.markdown("""
<div class="nature-card">
    <div class="section-title">💡 おでかけ前の対策チェック</div>
</div>
""", unsafe_allow_html=True)

st.checkbox("😷 花粉ガードマスクを着用した")
st.checkbox("👓 メガネ・サングラスを着用した")
st.checkbox("🧥 つるつるした素材の上着を選んだ")
st.checkbox("🧹 帰宅時に花粉を払う準備（ブラシ等）")

st.markdown("<br>", unsafe_allow_html=True)


# 5. 推薦理由（高野さんのデータ: data["advice"] を表示）
st.markdown(f"""
<div class="nature-card">
    <div class="section-title">📝 からだケアのアドバイス</div>
    <p style="color: #526355; line-height: 1.7; margin: 0;">
        {data['advice']}<br>
        帰宅時は玄関前で衣服の花粉を払い、手洗い・うがい・洗顔で目や鼻についた花粉を優しく洗い流しましょう。
    </p>
</div>
""", unsafe_allow_html=True)

st.caption("花粉対策ナビ - Natural Style UI v2.7 (関数連携対応版)")