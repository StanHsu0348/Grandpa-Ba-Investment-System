"""Private watchlist, with links back into each market's stock research."""
import pandas as pd
import streamlit as st
from src.watchlist import WatchlistError
from src.watchlist_ui import get_watchlist_store

owner = st.session_state.get('auth_username')
if not st.session_state.get('authenticated') or not owner:
    st.info('請重新登入後使用個人觀察清單。')
    st.stop()

st.title('我的觀察清單')
st.caption('把值得持續研究的企業留在這裡。清單依登入帳號分開保存。')
try:
    store = get_watchlist_store()
    entries = store.list(owner)
except WatchlistError:
    st.error('暫時無法讀取觀察清單，請稍後重試。')
    st.stop()

if store.backend == 'sqlite':
    st.info('目前清單儲存在這台主機；雲端重新部署後可能遺失。請管理者設定雲端資料庫以永久保存。')

if not entries:
    st.info('還沒有觀察股票。到台股或美股的個股詳情，點選「☆ 加入我的觀察清單」。')
    left, right = st.columns(2)
    if left.button('前往台股研究', use_container_width=True):
        st.switch_page('views/tw.py')
    if right.button('前往美股研究', use_container_width=True):
        st.switch_page('views/us.py')
    st.stop()

market = st.radio('市場', ['全部', '台股', '美股'], horizontal=True)
visible = [entry for entry in entries if market == '全部' or entry['market'] == {'台股': 'tw', '美股': 'us'}[market]]
st.caption(f'共 {len(entries)} 檔觀察股票 · 目前顯示 {len(visible)} 檔')
if not visible:
    st.info('這個市場尚未加入觀察股票。')
for entry in visible:
    code, name, actions = st.columns([1, 3, 2], vertical_alignment='center')
    code.markdown(('🇹🇼 ' if entry['market'] == 'tw' else '🇺🇸 ') + entry['symbol'])
    name.write(entry['company'])
    name.caption('加入日期：' + entry['added_at'][:10])
    with actions:
        study, remove = st.columns(2)
        identity = entry['market'] + '_' + entry['symbol']
        if study.button('個股研究', key='watch_open_' + identity, use_container_width=True):
            st.session_state[f"_{entry['market']}_research_symbol"] = entry['symbol']
            st.switch_page(f"views/{entry['market']}.py")
        if remove.button('移除', key='watch_remove_' + identity, use_container_width=True):
            try:
                store.remove(owner, entry['market'], entry['symbol'])
            except WatchlistError:
                st.error('移除失敗，請稍後重試。')
            else:
                st.rerun()

export = pd.DataFrame(entries).rename(columns={'market': '市場', 'symbol': '股票代碼', 'company': '公司名稱', 'added_at': '加入時間（UTC）'})
export['市場'] = export['市場'].map({'tw': '台股', 'us': '美股'})
st.download_button('下載我的觀察清單 CSV', export.to_csv(index=False).encode('utf-8-sig'),
                   file_name='my-watchlist.csv', mime='text/csv')
