# -*- coding: utf-8 -*-
"""
巴爺爺選股 — 五點好企業原則篩選系統（入口路由）

台股與美股是兩個完全獨立的頁面（views/tw.py、views/us.py），
各自讀取自己的 Excel、各自的篩選條件與 session_state，彼此不共用、不混合資料。
"""
import hmac

import streamlit as st

from src.theme import apply_theme, render_brand, render_principles

st.set_page_config(page_title="巴爺爺選股 — 五點好企業原則篩選系統", layout="wide")
apply_theme()


def _load_accounts() -> dict:
    """從 st.secrets 讀出所有可登入的 {帳號: 密碼}，密碼不進原始碼、不進 git。

    支援兩種寫法並可同時使用：
    - 舊版單一帳號：auth_username / auth_password（沿用至今的寫法，保留
      相容性，避免 Streamlit Cloud 上還沒更新成新格式的 Secrets 忽然失效）。
    - 新版多組帳號：[accounts] 區塊，可放任意組數的「帳號 = 密碼」，例如：
        [accounts]
        example_user = "YOUR_PASSWORD_HERE"
      兩種寫法可以同時存在，行為是「兩邊定義的帳號都能登入」。

    st.secrets 在完全沒有 secrets.toml（本機忘了建立、或 Streamlit Cloud
    忘了貼 Secrets）時，連 .get() 都會直接拋 StreamlitSecretNotFoundError，
    不會乖乖回傳預設值，所以要包 try/except 才能讓上層的防呆訊息生效。
    """
    accounts: dict = {}
    try:
        legacy_user = st.secrets.get("auth_username", "")
        legacy_pass = st.secrets.get("auth_password", "")
    except Exception:
        legacy_user = legacy_pass = ""
    if legacy_user and legacy_pass:
        accounts[legacy_user] = legacy_pass

    try:
        extra_accounts = st.secrets.get("accounts", {})
    except Exception:
        extra_accounts = {}
    for user, pw in dict(extra_accounts).items():
        if user and pw:
            accounts[user] = str(pw)

    return accounts


def check_login() -> bool:
    """帳號密碼比對 st.secrets，密碼不進原始碼、不進 git。

    刻意 fail closed：一組帳密都讀不到時（例如 Streamlit Cloud 忘了貼
    Secrets、或 key 名稱打錯），一律視為系統設定錯誤、直接擋下，不能讓
    「空帳密」被誤判成密碼比對成功。
    """
    if st.session_state.get("authenticated") and st.session_state.get("auth_username"):
        return True

    accounts = _load_accounts()
    if not accounts:
        st.error("系統尚未設定登入帳密（auth_username / auth_password 或 [accounts]），請聯絡管理員設定 Secrets。")
        return False

    render_brand()
    st.markdown('<section class="hero"><div class="eyebrow">A LONG-TERM PERSPECTIVE</div><h1>投資的從容，<br>從看懂一家好公司開始。</h1><p>以巴菲特的價值投資思維為靈感，專注企業品質，耐心看待價格。</p></section>', unsafe_allow_html=True)
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.subheader("歡迎回來")
        st.caption("登入後，開始探索台股與美股企業。")
        with st.form("login_form"):
            username = st.text_input("帳號", placeholder="輸入你的帳號")
            password = st.text_input("密碼", type="password", placeholder="輸入你的密碼")
            submitted = st.form_submit_button("登入研究室", type="primary", use_container_width=True)
    with right:
        st.markdown("### 好企業，值得細讀。")
        st.markdown("從歷年獲利到合理估價，讓每一次研究都有清楚的依據。")
        st.caption("台股與美股研究 · 五點原則檢核 · 同業比較")
    render_principles()

    if submitted:
        # hmac.compare_digest 對非 ASCII 字串（例如中文帳號）會直接拋
        # TypeError，因此比對前先統一編碼成 utf-8 bytes。逐一比對每組帳密，
        # 任一組吻合即算登入成功。
        matched = False
        if username and password:
            for valid_user, valid_pass in accounts.items():
                user_ok = hmac.compare_digest(username.encode("utf-8"), valid_user.encode("utf-8"))
                pass_ok = hmac.compare_digest(password.encode("utf-8"), str(valid_pass).encode("utf-8"))
                if user_ok and pass_ok:
                    matched = True
                    break
        if matched:
            st.session_state.clear()
            st.session_state.auth_username = username
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("帳號或密碼錯誤")

    return False


if not check_login():
    st.stop()

with st.sidebar:
    render_brand()
    if st.button("登出帳號", use_container_width=True):
        st.session_state.clear()
        st.rerun()

tw_page = st.Page("views/tw.py", title="台股", icon="🇹🇼", default=True)
us_page = st.Page("views/us.py", title="美股", icon="🇺🇸")

berkshire_page = st.Page("views/berkshire.py", title="波克夏持股", icon="🏛️")

watchlist_page = st.Page("views/watchlist.py", title="我的觀察清單", icon="⭐")

pg = st.navigation([tw_page, us_page, berkshire_page, watchlist_page])
pg.run()
st.markdown('<footer class="site-footer">巴爺爺選股 · GRANDPA BA INVESTOR<br>以價值投資理念為靈感的獨立研究工具，與 Berkshire Hathaway 無隸屬或背書關係。</footer>', unsafe_allow_html=True)
