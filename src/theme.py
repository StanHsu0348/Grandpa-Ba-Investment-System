"""Shared visual system and editorial components for both markets."""
from html import escape
import streamlit as st

_CSS = """
<style>
[data-testid="stMainBlockContainer"] {max-width:1240px;padding:2.5rem 3rem 4rem;}
h1,h2,h3 {letter-spacing:-.035em;}
[data-testid="stSidebar"] h2 {font-size:1rem;letter-spacing:0;}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {gap:.85rem;}
[data-testid="stSidebar"] hr {margin:.6rem 0;}
[data-testid="stTabs"] [data-baseweb="tab-list"] {gap:6px;padding:5px;background:rgba(125,130,120,.1);border-radius:999px;width:fit-content;max-width:100%;}
[data-testid="stTabs"] [data-baseweb="tab-highlight"], [data-testid="stTabs"] [data-baseweb="tab-border"] {display:none;}
[data-testid="stTabs"] button[data-baseweb="tab"] {height:44px;border-radius:999px;padding:0 22px;white-space:nowrap;}
[data-testid="stTabs"] button[aria-selected="true"] {background:#244c3c;color:#fff;box-shadow:0 2px 8px #152d2515;}
[data-testid="stTabs"] [data-baseweb="tab-panel"] {padding-top:1.6rem;}
[data-testid="stMetricValue"] {font-variant-numeric:tabular-nums;letter-spacing:-.045em;font-weight:600;}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius:20px;}
[data-testid="stDataFrame"] {border-radius:16px;overflow:hidden;}
.stButton button,.stDownloadButton button,.stLinkButton a {min-height:44px;transition:box-shadow .18s ease,transform .18s ease;}
.stButton button:hover,.stDownloadButton button:hover,.stLinkButton a:hover {box-shadow:0 4px 16px #244c3c18;transform:translateY(-1px);}
button:focus-visible,a:focus-visible,input:focus-visible {outline:3px solid #a88547!important;outline-offset:3px;}
.brand {display:flex;align-items:center;gap:12px;margin-bottom:1.2rem;}
.brand-mark {display:grid;place-items:center;width:38px;height:38px;border-radius:50%;background:#244c3c;color:#f5efdf;font:23px Georgia,serif;}
.brand-name {font-weight:650;font-size:17px;letter-spacing:.04em;}
.brand small {display:block;font:10px Georgia,serif;letter-spacing:.16em;color:#7b806f;margin-top:3px;}
.hero {position:relative;overflow:hidden;border:1px solid #244c3c12;border-radius:28px;background:linear-gradient(110deg,#f0eee5,#e6ece5);padding:42px 44px;margin:0 0 20px;color:#203b30;}
.eyebrow {font-size:11px;letter-spacing:.2em;font-weight:650;color:#677452;text-transform:uppercase;}
.hero h1 {font-size:clamp(32px,4vw,54px);line-height:1.22;margin:16px 0!important;padding:0;max-width:700px;font-weight:650;color:#203b30;}
.hero p {max-width:660px;font-size:15px;line-height:1.85;margin:0;color:#58645a;}
.hero-meta {display:flex;flex-wrap:wrap;gap:12px 24px;margin-top:26px;font-size:12px;color:#526353;}
.hero-meta span {border-top:1px solid #244c3c25;padding-top:12px;}
.hero-seal {position:absolute;right:30px;top:30px;border:1px solid #a58e5d66;border-radius:50%;width:70px;height:70px;display:grid;place-items:center;font:italic 32px Georgia,serif;color:#8f7b50;opacity:.6;}
.principles {display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:24px 0;}
.principle {padding:26px;border:1px solid #7c806525;border-radius:20px;}
.principle span {font:italic 23px Georgia,serif;color:#9c8554;}
.principle h3 {font-size:17px;margin:15px 0 8px;padding:0;}
.principle p {font-size:14px;line-height:1.8;opacity:.7;margin:0;}
[data-testid="stMain"] {scroll-behavior:smooth;}
#us-page-top,#tw-page-top {scroll-margin-top:5rem;}
.back-to-top-row {display:flex;justify-content:flex-end;margin-top:24px;padding-top:20px;border-top:1px solid #7c806530;}
a.back-to-top,a.back-to-top:visited {display:inline-flex;align-items:center;gap:10px;min-height:48px;padding:0 20px;border:1px solid #7c806540;border-radius:999px;background:rgba(125,130,120,.08);color:inherit;text-decoration:none;font-size:14px;font-weight:600;transition:background .18s ease,box-shadow .18s ease,transform .18s ease;}
a.back-to-top:hover {color:inherit;text-decoration:none;background:rgba(125,130,120,.16);box-shadow:0 4px 14px #244c3c14;transform:translateY(-2px);}
a.back-to-top:active {transform:translateY(0);box-shadow:none;}
a.back-to-top:focus-visible {outline:3px solid #a88547;outline-offset:4px;}
.back-to-top-icon {display:grid;place-items:center;width:26px;height:26px;border-radius:50%;background:#244c3c;color:#fff;font-size:18px;line-height:1;}
.site-footer {margin-top:40px;padding-top:18px;border-top:1px solid #7c806530;font-size:11px;opacity:.65;letter-spacing:.04em;line-height:1.8;}
@media(max-width:768px) {
 [data-testid="stMainBlockContainer"] {padding:1.5rem 1rem 3rem;}
 .hero {padding:28px 22px;border-radius:22px;} .hero-seal {display:none;}
 .hero h1 {font-size:34px;} .principles {grid-template-columns:1fr;gap:10px;}
 .principle {padding:20px;} [data-testid="stTabs"] button[data-baseweb="tab"] {padding:0 14px;font-size:14px;}
}
@media(prefers-reduced-motion:reduce) {*,*::before,*::after {transition:none!important;scroll-behavior:auto!important;}}
</style>
"""


def apply_theme() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def render_brand() -> None:
    st.markdown('<div class="brand"><span class="brand-mark" aria-hidden="true">B.</span><div class="brand-name">巴爺爺選股<small>GRANDPA BA INVESTOR</small></div></div>', unsafe_allow_html=True)


def render_hero(market: str, date: str, total: int, matched: int) -> None:
    st.markdown(f"""<section class="hero"><div class="eyebrow">GRANDPA BA INVESTOR · {escape(market)}研究室</div>
<h1>發現好企業。<br>讓時間，成為你的優勢。</h1>
<p>從穩定獲利、現金分配到合理價格，<br>用五點好企業原則，建立自己的長期投資判斷。</p>
<div class="hero-meta"><span>{escape(market)} · {total:,} 家企業</span><span>{matched:,} 家符合目前篩選</span><span>資料收盤日 {escape(str(date))} · 非即時</span></div>
<div class="hero-seal" aria-hidden="true">B.</div></section>""", unsafe_allow_html=True)


def render_principles() -> None:
    st.markdown("""<div class="principles">
<article class="principle"><span>01 / Quality</span><h3>先看懂，再持有。</h3><p>查詢一家企業，從五年 ROE 與現金分配，了解生意的品質。</p></article>
<article class="principle"><span>02 / Discipline</span><h3>讓標準，先於選擇。</h3><p>在側欄設定門檻，再到企業篩選比較符合條件的公司。</p></article>
<article class="principle"><span>03 / Patience</span><h3>為價值，保留耐心。</h3><p>搭配估價區間與預期報酬率，並完成需要人工查證的項目。</p></article>
</div>""", unsafe_allow_html=True)
