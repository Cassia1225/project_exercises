import streamlit as st

st.set_page_config(page_title="画面の流れプロトタイプ", layout="centered")

st.caption("画面の流れプロトタイプ (UI担当：馬場)")
st.title("花粉対策ナビ プロトタイプ")

# 1. 外出情報
st.subheader("今日の外出情報")
st.info("📍 千葉県 習志野市  |  🕒 14:00〜16:00")

# 2. 花粉対策レベル
st.subheader("花粉対策レベル")
st.error("## 【 高い 】")

# 3. 詳細データ
st.subheader("詳細データ")
col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="🌸 花粉", value="取得中...")
with col2:
    st.metric(label="☀️ 天気", value="取得中...")
with col3:
    st.metric(label="💨 風速", value="取得中...")
st.caption("※ APIデータ連携後に表示されます")

# 4. おすすめの対策
st.subheader("おすすめの対策")
st.write("😷 マスク")
st.write("👓 メガネ")
st.write("🧥 花粉が付きにくい上着")
st.write("🧹 帰宅時に衣服の花粉を落とす")

# 5. 推薦理由
st.subheader("推薦理由")
st.success("花粉飛散量が非常に多く、風も強いため、外出時の対策強化を推奨します。")
