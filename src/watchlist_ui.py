"""Watchlist controls use only the authenticated session's account identity."""
import streamlit as st
from src.watchlist import WatchlistStore, WatchlistError


def get_watchlist_store():
    try:
        database_url = st.secrets.get('WATCHLIST_DATABASE_URL')
    except FileNotFoundError:
        database_url = None
    return WatchlistStore(database_url=database_url)


def render_watchlist_button(market, symbol, company, key_prefix):
    owner = st.session_state.get('auth_username')
    if not st.session_state.get('authenticated') or not owner:
        return
    try:
        store = get_watchlist_store()
        saved = store.contains(owner, market, symbol)
        label = '★ 已加入觀察清單 · 移除' if saved else '☆ 加入我的觀察清單'
        if st.button(label, key=f'{key_prefix}_watch_{symbol}'):
            if saved:
                store.remove(owner, market, symbol)
            else:
                store.add(owner, market, symbol, company)
            st.rerun()
    except WatchlistError:
        st.warning('觀察清單暫時無法儲存或讀取，請稍後重試。')
