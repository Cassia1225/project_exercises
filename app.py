import streamlit as st

st.title('test screen')
name = st.text_input('input name :')

if st.button("あいさつする"):
    st.success(f"こんにちは、{name}さん！")