# -*- coding: utf-8 -*-
"""
Apple 風格視覺補強。

色彩、圓角、字體、資料表邊框、卡片邊框（st.container(border=True)）等
「主題層級」的設定交給 `.streamlit/config.toml` 處理（Streamlit 原生支援
淺色／深色兩套配色，並會依使用者系統設定或手動切換自動套用）。這個模組
只補強 config.toml 管不到的細節：分頁改成膠囊式切換（segmented control）、
按鈕的互動回饋、主內容區留白。

只在 app.py 呼叫一次（在 `pg.run()` 之前），台股／美股頁面都會套用到，
不需要在 views/tw.py、views/us.py 裡各自重複注入。
"""
import streamlit as st

_CSS = """
<style>
/* 主內容區留白加大，仿 Apple 官網式的大留白排版 */
[data-testid="stMainBlockContainer"] {
    padding-top: 2.5rem;
    padding-bottom: 3rem;
    max-width: 1200px;
}

/* 分頁改成膠囊式切換（segmented control），取代預設的底線分頁樣式 */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 2px;
    background-color: rgba(120, 120, 128, 0.12);
    padding: 4px;
    border-radius: 999px;
    width: fit-content;
}
[data-testid="stTabs"] [data-baseweb="tab-highlight"],
[data-testid="stTabs"] [data-baseweb="tab-border"] {
    display: none;
}
[data-testid="stTabs"] button[data-baseweb="tab"] {
    height: 2.5rem;
    border-radius: 999px;
    padding: 0 1.25rem;
    font-weight: 500;
    transition: background-color 0.2s ease, box-shadow 0.2s ease;
}
/* 選中分頁的底色故意不分「淺色/深色模式」兩套寫死顏色（原本用
   @media (prefers-color-scheme: dark) 判斷），因為 Streamlit 的淺色／
   深色其實有兩種切換來源：跟隨系統設定（會反映在 prefers-color-scheme），
   以及使用者在右上角選單手動選 Light/Dark（不會反映在 prefers-color-scheme，
   Streamlit 也沒有在 DOM 上留下任何 data-theme 屬性或 CSS 變數可供判斷）。
   實測：系統為淺色、手動選單選「Dark」時，頁面背景會確實變深色，但這裡
   若照 prefers-color-scheme 判斷會誤判成淺色，選中分頁變成一顆刺眼的
   白色藥丸浮在深色頁面上。改用中性半透明灰階＋邊框，疊在淺色或深色底色
   上都有適度對比，不需要判斷目前是哪個模式。 */
[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
    background-color: rgba(120, 120, 128, 0.28);
    border: 1px solid rgba(120, 120, 128, 0.24);
}

/* 指標大數字的字距收緊一點，貼近 Apple Stocks 的大數字排版 */
[data-testid="stMetricValue"] {
    letter-spacing: -0.02em;
}

/* 按鈕互動回饋：hover 時微微上浮＋加深陰影，貼近 iOS 按壓回饋的手感 */
.stButton button, .stDownloadButton button, .stLinkButton a {
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.stButton button:hover, .stDownloadButton button:hover, .stLinkButton a:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(0, 113, 227, 0.25);
}

/* 標題字距收緊，大字級標題貼近 Apple 的緊排版風格 */
h1, h2, h3 {
    letter-spacing: -0.01em;
}
</style>
"""


def apply_theme() -> None:
    """注入 Apple 風格的補強樣式（色彩／圓角／字體主要交給 config.toml）。"""
    st.markdown(_CSS, unsafe_allow_html=True)
