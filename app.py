import streamlit as st

def main():
    st.title('test screen')
    name = st.text_input('input name :')

    if st.button("あいさつする"):
        st.success(f"こんにちは、{name}さん！")
    
if __name__ == "__main__":
    main()