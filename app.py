import streamlit as st

# --- ページ基本設定 ---
st.set_page_config(
    page_title="花粉対策ナビ",
    page_icon="🌸",
    layout="centered"
)

# --- カスタムCSS（デザイン・背景色・カード風スタイル） ---
st.markdown("""
<style>
    /* 全体の背景色 */
    .stApp {
        background-color: #f4f7f6;
    }
    
    /* カード風の白い枠組み */
    .custom-card {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        margin-bottom: 20px;
        border-left: 5px solid #4CAF50;
    }
    
    .danger-card {
        border-left: 5px solid #FF5252;
    }

    /* タイトルの文字色 */
    .main-title {
        color: #2C3E50;
        font-weight: bold;
        text-align: center;
        margin-bottom: 25px;
    }
    
    /* サブタイトルの強調 */
    .section-title {
        color: #34495E;
        font-size: 1.1rem;
        font-weight: bold;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# --- タイトル ---
st.markdown("<h1 class='main-title'>🌸 花粉対策ナビ</h1>", unsafe_allow_html=True)

# ---------------------------------------------------------
# 側列（サイドバー）：アレルギー入力UI＆設定
# ---------------------------------------------------------
st.sidebar.header("⚙️ ユーザー設定")

# 1. アレルギー選択フォーム
selected_allergies = st.sidebar.multiselect(
    "該当するアレルギーを選択",
    ["スギ", "ヒノキ", "ブタクサ", "シラカバ", "カモガヤ", "未登録 / わからない"],
    default=["スギ"]
)

# 2. 地域・時間の簡易入力（※将来の拡張用）
st.sidebar.markdown("---")
location = st.sidebar.text_input("地域", value="千葉県 習志野市")
time_slot = st.sidebar.selectbox("外出予定の時間帯", ["10:00 〜 12:00", "12:00 〜 14:00", "14:00 〜 16:00", "16:00 〜 18:00"], index=2)


# ---------------------------------------------------------
# メイン画面
# ---------------------------------------------------------

# 1. 今日の外出情報
st.markdown(f"""
<div class="custom-card">
    <div class="section-title">📍 今日の外出情報</div>
    <p style="font-size: 1.1rem; margin: 0;"><b>地域:</b> {location} &nbsp;|&nbsp; <b>時間:</b> {time_slot}</p>
</div>
""", unsafe_allow_html=True)


# 2. 花粉対策レベル＆アレルギー特化アラート
st.markdown("""
<div class="custom-card danger-card">
    <div class="section-title">🚨 花粉対策レベル</div>
    <h2 style="color: #FF5252; margin: 5px 0;">【 高い 】</h2>
</div>
""", unsafe_allow_html=True)

# アレルギー入力に応じた動的メッセージ
if "未登録 / わからない" not in selected_allergies and len(selected_allergies) > 0:
    allergies_text = "・".join(selected_allergies)
    st.warning(f"⚠️ **【アレルギー注意報】** 現在 **{allergies_text}** の飛散レベルが高くなっています。十分な対策を推奨します。")


# 3. 詳細データ（API連携エリア）
st.subheader("📊 詳細データ")
col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="🌸 花粉", value="取得中...")
with col2:
    st.metric(label="☀️ 天気", value="取得中...")
with col3:
    st.metric(label="💨 風速", value="取得中...")
st.caption("※ 池田くん・大高くんのAPIと連携後に自動更新されます")

st.markdown("<br>", unsafe_allow_html=True)


# 4. おすすめの対策
st.markdown("""
<div class="custom-card">
    <div class="section-title">💡 おすすめの対策</div>
    <ul style="line-height: 1.8;">
        <li>😷 <b>マスクの着用</b>（必須）</li>
        <li>👓 <b>花粉ガードメガネ</b></li>
        <li>🧥 <b>花粉が付きにくい素材の上着</b></li>
        <li>🧹 <b>帰宅時に衣服の花粉をしっかり払い落とす</b></li>
    </ul>
</div>
""", unsafe_allow_html=True)


# 5. 推薦理由
st.markdown("""
<div class="custom-card">
    <div class="section-title">📝 推薦理由</div>
    <p style="color: #555; margin: 0;">
        本日は花粉飛散量が非常に多く、風速も強いため、外出時の花粉付着リスクが高まっています。
        アレルギー症状の悪化を防ぐため、上記の対策強化を推奨します。
    </p>
</div>
""", unsafe_allow_html=True)

# チーム向けフッター
st.caption("UIプロトタイプ v2.0 (アレルギー入力対応版)")