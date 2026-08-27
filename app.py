# -*- coding: utf-8 -*-
"""
巴爺爺選股 — 五點好企業原則篩選系統（入口路由）

台股與美股是兩個完全獨立的頁面（views/tw.py、views/us.py），
各自讀取自己的 Excel、各自的篩選條件與 session_state，彼此不共用、不混合資料。
"""
import hmac

import streamlit as st

from src.theme import apply_theme

st.set_page_config(page_title="巴爺爺選股 — 五點好企業原則篩選系統", layout="wide")
apply_theme()


def check_login() -> bool:
    """帳號密碼比對 st.secrets，密碼不進原始碼、不進 git。

    刻意 fail closed：secrets 沒設定或設成空字串時（例如 Streamlit Cloud
    忘了貼 Secrets、或 key 名稱打錯），一律視為系統設定錯誤、直接擋下，
    不能讓「兩邊都是空字串」被誤判成密碼比對成功。
    """
    if st.session_state.get("authenticated"):
        return True

    valid_user = st.secrets.get("auth_username", "")
    valid_pass = st.secrets.get("auth_password", "")
    if not valid_user or not valid_pass:
        st.error("系統尚未設定登入帳密（auth_username / auth_password），請聯絡管理員設定 Secrets。")
        return False

    st.markdown("## 🔒 登入")
    with st.form("login_form"):
        username = st.text_input("帳號")
        password = st.text_input("密碼", type="password")
        submitted = st.form_submit_button("登入")

    if submitted:
        user_ok = hmac.compare_digest(username, valid_user)
        pass_ok = hmac.compare_digest(password, valid_pass)
        if username and password and user_ok and pass_ok:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("帳號或密碼錯誤")

    return False


if not check_login():
    st.stop()

with st.sidebar:
    if st.button("登出"):
        st.session_state.authenticated = False
        st.rerun()

tw_page = st.Page("views/tw.py", title="台股", icon="🇹🇼", default=True)
us_page = st.Page("views/us.py", title="美股", icon="🇺🇸")

pg = st.navigation([tw_page, us_page])
pg.run()
