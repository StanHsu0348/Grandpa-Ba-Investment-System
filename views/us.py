# -*- coding: utf-8 -*-
"""
巴爺爺選股 — 美股頁面（五點好企業原則篩選系統）

與台股頁面（views/tw.py）邏輯相同，皆以課程「五點好企業原則」為核心，
但資料來源、篩選門檻與部分細節針對美股清單（uslist.xlsx）獨立調整，
兩者的資料與 session_state 完全分開，不共用、不混合。
"""
import io
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from src.constants import (
    COVERAGE_AUTO_ITEMS,
    COVERAGE_TOTAL,
    CURRENCY_CAVEAT_NOTE,
    DEFAULT_IRR_THRESHOLD_US,
    DEFAULT_MARKET_CAP_THRESHOLD_US,
    DEFAULT_NET_INCOME_THRESHOLD_US,
    DEFAULT_PAYOUT_THRESHOLD_US,
    DEFAULT_ROE_THRESHOLD_US,
    IRR_QUICK_OPTIONS_US,
    IRR_SLIDER_MAX,
    IRR_SLIDER_MIN,
    MANUAL_CHECK_NOTE_US,
    NET_INCOME_QUICK_OPTIONS_US,
    PAYOUT_QUICK_OPTIONS_US,
    ROE_COLS_RECENT_TO_OLD,
    ROE_YEAR_LABELS_OLD_TO_NEW,
    YAHOO_FINANCE_URL_TEMPLATE,
)
from src.data_loader import DataLoadError, get_data_date, load_us_data
from src.scoring import compute_coverage_score, compute_roe_stability
from src.screener import (
    ROE_FILTER_MODE_LABELS,
    ROE_FILTER_MODES,
    apply_all_filters,
    filter_by_roe,
    valuation_labels,
)
from src.ui_helpers import synced_slider
from src.us_sector_i18n import (
    US_SECTOR_GROUPS,
    format_group_option,
    format_sector_option,
    group_of as us_group_of,
    translate as us_translate,
)

DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "uslist.xlsx"
)


# ---------------------------------------------------------------------------
# 資料載入（含快取）
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="讀取資料中…")
def _load_from_path(path: str, mtime: float) -> pd.DataFrame:
    return load_us_data(path)


@st.cache_data(show_spinner="讀取資料中…")
def _load_from_bytes(file_bytes: bytes) -> pd.DataFrame:
    return load_us_data(io.BytesIO(file_bytes))


@st.cache_data(show_spinner=False)
def _to_csv_bytes(table: pd.DataFrame) -> bytes:
    return table.to_csv(index=False).encode("utf-8-sig")


@st.cache_data(show_spinner=False)
def _to_excel_bytes(table: pd.DataFrame) -> bytes:
    """把篩選結果表轉成 Excel bytes，供下載按鈕使用。

    這裡加上 @st.cache_data 是因為 st.download_button 每次 script rerun
    都要重新取得 data= 參數（哪怕使用者根本沒按下載），而 ExcelWriter
    對上萬列資料的寫入成本不小（實測美股 12,497 列約 2 秒），
    不快取的話等於每次調整任何篩選條件都要白白付這筆成本。
    快取鍵是 table 本身的內容雜湊，篩選結果不變時直接吃快取。
    傳入的 table 需為欄位皆為純量值的版本（可直接寫入 Excel）。
    """
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        table.to_excel(writer, index=False, sheet_name="篩選結果")
    return excel_buffer.getvalue()


def init_session_defaults():
    defaults = {
        "us_roe_mode": "strict",
        "us_roe_threshold_slider": 0.0,
        "us_roe_threshold_input": 0.0,
        "us_payout_threshold_slider": 0.0,
        "us_payout_threshold_input": 0.0,
        "us_net_income_threshold": 0.0,
        "us_sector_groups": None,  # None 代表尚未依資料初始化
        "us_sectors": None,  # None 代表尚未依資料初始化
        "us_currencies": None,  # None 代表尚未依資料初始化
        "us_valuation_mode": "any",
        "us_irr_threshold_slider": IRR_SLIDER_MIN,
        "us_irr_threshold_input": IRR_SLIDER_MIN,
        "us_detail_symbol": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def clear_all_filters(all_sectors, all_currencies):
    """
    重設所有篩選條件，包含已實例化的 widget key。

    注意：Streamlit 不允許在一個 widget 已於本次 script run 建立之後，
    再修改其對應的 session_state key。因此這個函式必須在任何側邊欄
    widget 建立「之前」呼叫（見下方 `_us_clear_filters_pending` 的處理方式）。
    """
    st.session_state["us_roe_mode"] = "strict"
    st.session_state["us_roe_threshold_slider"] = 0.0
    st.session_state["us_roe_threshold_input"] = 0.0
    st.session_state["us_payout_threshold_slider"] = 0.0
    st.session_state["us_payout_threshold_input"] = 0.0
    st.session_state["us_net_income_threshold"] = 0.0
    st.session_state["us_sector_groups"] = list(US_SECTOR_GROUPS.keys())
    st.session_state["us_sectors"] = list(all_sectors)
    st.session_state["us_currencies"] = list(all_currencies)
    st.session_state["us_valuation_mode"] = "any"
    st.session_state["us_irr_threshold_slider"] = IRR_SLIDER_MIN
    st.session_state["us_irr_threshold_input"] = IRR_SLIDER_MIN


def render_stock_detail(row: pd.Series, df: pd.DataFrame, roe_threshold: float, key_prefix: str) -> None:
    """渲染單一股票的詳細卡片：5年 ROE 趨勢圖、五點原則逐項檢核、同業比較。

    df 為完整資料集（不受目前篩選條件影響），用於同業比較；
    key_prefix 用於區隔不同呼叫端產生的 widget key（例如快速查詢 vs 篩選結果選單），
    避免同一次 script run 中出現重複的 widget key。
    """
    detail_cols = st.columns([1, 1])

    with detail_cols[0], st.container(border=True):
        years_old_to_new = list(reversed(ROE_COLS_RECENT_TO_OLD))
        roe_values = [row[c] for c in years_old_to_new]
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=ROE_YEAR_LABELS_OLD_TO_NEW,
                y=roe_values,
                mode="lines+markers",
                name="ROE(%)",
            )
        )
        fig.add_hline(y=roe_threshold, line_dash="dash", line_color="gray",
                       annotation_text=f"門檻 {roe_threshold}%")
        fig.update_layout(title=f"{row['COMPANY']} 5年 ROE 趨勢", yaxis_title="ROE (%)", height=350)
        st.plotly_chart(fig, width="stretch", key=f"{key_prefix}_roe_chart")

        stability = compute_roe_stability(row)
        st.caption(
            f"標準差：{stability['std']:.2f}　"
            f"趨勢分類：{stability['trend_label']}　"
            f"可用年數：{stability['n_years']}/5"
            if pd.notna(stability["std"])
            else f"趨勢分類：{stability['trend_label']}"
        )

    with detail_cols[1], st.container(border=True):
        st.markdown("**五點原則逐項檢核**")
        roe_ok = None if pd.isna(row["預期ROE"]) or roe_threshold <= 0 else row["預期ROE"] >= roe_threshold
        payout_ok = row["預期配息率"] >= DEFAULT_PAYOUT_THRESHOLD_US
        market_cap_ok = None if pd.isna(row["市值($m)"]) else row["市值($m)"] >= DEFAULT_MARKET_CAP_THRESHOLD_US

        def mark(ok):
            if ok is None:
                return "⚠️"
            return "✅" if ok else "❌"

        roe_text = "—（無資料）" if pd.isna(row["預期ROE"]) else f"{row['預期ROE']:.2f}%"
        roe_history_text = " / ".join(
            "—" if pd.isna(row[c]) else f"{row[c]:.1f}%" for c in ROE_COLS_RECENT_TO_OLD
        )
        st.markdown(
            f"- {mark(roe_ok)} ①ROE穩定：預期ROE {roe_text}（門檻 {roe_threshold}%）　"
            f"｜　歷年ROE(近→遠) {roe_history_text}"
        )
        retention_text = "—" if pd.isna(row["盈再率"]) else f"{row['盈再率']:.2f}%"
        st.markdown(
            f"- {mark(payout_ok)} ②配得出現金：配息率 {row['預期配息率']:.2f}%"
            f"（課程門檻 {DEFAULT_PAYOUT_THRESHOLD_US}%），盈再率 {retention_text}"
        )
        sector_display = f"{us_translate(row['SECTOR'])}（{row['SECTOR']}）" if pd.notna(row["SECTOR"]) else "—"
        industry_display = row["Industry"] if pd.notna(row["Industry"]) else "—"
        st.markdown(
            f"- ⚠️ ③不會變的公司：Sector「{sector_display}」／Industry「{industry_display}」，請自行判斷"
        )
        # 注意：st.markdown 會把「$…$」解讀成 LaTeX 數學公式語法，兩個裸的
        # 錢字號同一行會讓中間文字被吃掉、跑出奇怪的等寬字樣式，因此這裡
        # 跟著本檔案其他地方（例如淨利門檻說明）的慣例改用「USD」文字，
        # 不直接輸出「$」符號。
        market_cap_text = "—（無資料）" if pd.isna(row["市值($m)"]) else f"USD {row['市值($m)']:.1f}M"
        st.markdown(
            f"- {mark(market_cap_ok)} ④公司夠大：市值 {market_cap_text}"
            f"（門檻 USD {DEFAULT_MARKET_CAP_THRESHOLD_US:.0f}M），上市年資 ❌ 待查證"
        )
        st.markdown("- ❌ ⑤老闆誠信：內部人（董監）持股 待查證")

        irr_text = "—（無法估算）" if pd.isna(row["預期報酬率"]) else f"{row['預期報酬率']:.1f}%"
        irr_ok = None if pd.isna(row["預期報酬率"]) else row["預期報酬率"] >= DEFAULT_IRR_THRESHOLD_US
        st.markdown(
            f"- {mark(irr_ok)} 延伸判準：預期報酬率(IRR) {irr_text}"
            f"（課程門檻 ≥{DEFAULT_IRR_THRESHOLD_US:.0f}%）"
        )

        yahoo_url = YAHOO_FINANCE_URL_TEMPLATE.format(symbol=row["Symbol"])
        st.link_button("前往 Yahoo Finance 查證 ④⑤", yahoo_url, key=f"{key_prefix}_yahoo_link")

    st.divider()
    if pd.isna(row["Industry"]):
        st.caption("此公司無細分產業（Industry）資料，無法進行同業比較。")
    else:
        with st.container(border=True):
            peers = df[df["Industry"] == row["Industry"]].copy()
            peers = peers.sort_values("市值($m)", ascending=False, na_position="last").reset_index(drop=True)
            peers.insert(0, "排名", peers.index + 1)
            peers["本股"] = peers["Symbol"].apply(lambda s: "👉" if s == row["Symbol"] else "")

            my_rank_rows = peers.index[peers["Symbol"] == row["Symbol"]]
            my_rank = int(my_rank_rows[0]) + 1 if len(my_rank_rows) else None
            total_peers = len(peers)

            st.markdown(f"**同業比較 — {row['Industry']}（Industry，共 {total_peers} 家，依市值排序）**")
            if my_rank and pd.notna(row["市值($m)"]):
                st.caption(f"{row['COMPANY']} 市值約 {row['市值($m)']:.1f} 百萬美元，同業市值排名第 {my_rank}/{total_peers} 名")

            peer_show_cols = {
                "本股": "本股",
                "排名": "排名",
                "Symbol": "股票代號",
                "COMPANY": "公司名稱",
                "市值($m)": "市值($M)",
                "預期ROE": "預期ROE(%)",
                "預期配息率": "配息率(%)",
                "預期常利": "淨利(百萬,原幣)",
            }
            peer_table = peers[list(peer_show_cols.keys())].rename(columns=peer_show_cols)
            st.dataframe(
                peer_table,
                width="stretch",
                hide_index=True,
                height=350,
                key=f"{key_prefix}_peer_table",
                column_config={
                    "市值($M)": st.column_config.NumberColumn(format="%.1f"),
                    "預期ROE(%)": st.column_config.NumberColumn(format="%.2f"),
                    "配息率(%)": st.column_config.NumberColumn(format="%.2f"),
                    "淨利(百萬,原幣)": st.column_config.NumberColumn(format="%.1f"),
                },
            )

    st.markdown("[⬆️ 回到最上方](#us-page-top)")


init_session_defaults()

# ---------------------------------------------------------------------------
# 側邊欄：資料來源
# ---------------------------------------------------------------------------
st.sidebar.header("📁 資料來源（美股）")
uploaded_file = st.sidebar.file_uploader("上傳最新股票清單 Excel", type=["xlsx"], key="us_uploader")

try:
    if uploaded_file is not None:
        df = _load_from_bytes(uploaded_file.getvalue())
        source_label = f"上傳檔案：{uploaded_file.name}"
    else:
        if not os.path.exists(DATA_PATH):
            st.error(f"找不到預設資料檔：{DATA_PATH}，請於側邊欄上傳 Excel 檔案。")
            st.stop()
        df = _load_from_path(DATA_PATH, os.path.getmtime(DATA_PATH))
        source_label = "預設資料：data/uslist.xlsx"
except DataLoadError as exc:
    st.error(f"資料讀取失敗：{exc}")
    st.stop()

data_date = get_data_date(df)
st.sidebar.caption(f"目前資料來源：{source_label}")
st.sidebar.caption(f"資料日期（收盤日）：{data_date}")

all_sectors = sorted(df["SECTOR"].dropna().unique().tolist())
all_currencies = sorted(df["財報幣別"].dropna().unique().tolist())
if st.session_state["us_currencies"] is None:
    st.session_state["us_currencies"] = list(all_currencies)

# 「清空所有篩選」必須在任何篩選 widget 建立之前套用，見 clear_all_filters() 註解
if st.session_state.get("_us_clear_filters_pending"):
    clear_all_filters(all_sectors, all_currencies)
    st.session_state["_us_clear_filters_pending"] = False

st.sidebar.divider()

# ---------------------------------------------------------------------------
# 側邊欄：① ROE 穩定度篩選
# ---------------------------------------------------------------------------
st.sidebar.header("① ROE 穩定度篩選")
st.sidebar.caption(
    f"近5年（ROE1~ROE5 實際歷史值，非預期ROE）依所選模式與門檻篩選，"
    f"缺值視為不通過。門檻設為 0 代表不限。（課程門檻參考值：{DEFAULT_ROE_THRESHOLD_US:.0f}%）"
)

roe_mode = st.sidebar.radio(
    "篩選模式",
    options=ROE_FILTER_MODES,
    format_func=lambda m: ROE_FILTER_MODE_LABELS[m],
    key="us_roe_mode",
)
roe_threshold = synced_slider("ROE 門檻（%，0=不限）", "us_roe_threshold", 0.0, 40.0, 0.5)
st.sidebar.caption(f"目前模式與門檻下符合 {len(filter_by_roe(df, roe_threshold, roe_mode)):,} 家")
st.sidebar.caption("⚠️ ROE1~ROE5 的「近→遠」順序沿用台股清單的假設，尚未針對美股個別驗證，僅供參考。")

st.sidebar.divider()

# ---------------------------------------------------------------------------
# 側邊欄：② 配息率篩選
# ---------------------------------------------------------------------------
st.sidebar.header("② 配息率篩選")
payout_cols = st.sidebar.columns(len(PAYOUT_QUICK_OPTIONS_US))
for col, (label, value) in zip(payout_cols, PAYOUT_QUICK_OPTIONS_US.items()):
    if col.button(label, key=f"us_payout_quick_{label}"):
        st.session_state["us_payout_threshold_slider"] = value
        st.session_state["us_payout_threshold_input"] = value

payout_threshold = synced_slider("配息率門檻（%，0=不限）", "us_payout_threshold", 0.0, 100.0, 1.0)

st.sidebar.divider()

# ---------------------------------------------------------------------------
# 側邊欄：④ 淨利門檻
# ---------------------------------------------------------------------------
st.sidebar.header("④ 淨利門檻（公司夠大）")
st.sidebar.caption(
    f"美股改用課程附錄「稅前淨利國際級 > USD {DEFAULT_NET_INCOME_THRESHOLD_US:.0f}M」延伸判準，"
    "而非台股的 5 億元台幣門檻。"
)
net_income_cols = st.sidebar.columns(len(NET_INCOME_QUICK_OPTIONS_US))
for col, (label, value) in zip(net_income_cols, NET_INCOME_QUICK_OPTIONS_US.items()):
    if col.button(label, key=f"us_ni_quick_{label}"):
        st.session_state["us_net_income_threshold"] = value

net_income_threshold = st.sidebar.number_input(
    "淨利門檻（百萬元，依財報幣別，0=不限）", min_value=0.0, step=25.0, key="us_net_income_threshold"
)

st.sidebar.caption("「上市滿 2 年」資料中無此欄位，不做篩選，請自行查證。")
st.sidebar.divider()

# ---------------------------------------------------------------------------
# 側邊欄：延伸判準 — 預期報酬率（IRR）（非五點原則本身，預設收合）
# ---------------------------------------------------------------------------
with st.sidebar.expander("🎯 延伸判準：預期報酬率（IRR）", expanded=False):
    st.caption(
        f"對應課程 Ch6「合理買價報酬率」概念，課程延伸判準為 IRR ≥ {DEFAULT_IRR_THRESHOLD_US:.0f}%。"
        "滑到最左（不限）時不套用；套用時，無法估算 IRR 的公司會被排除。"
    )
    irr_cols = st.columns(len(IRR_QUICK_OPTIONS_US))
    for col, (label, value) in zip(irr_cols, IRR_QUICK_OPTIONS_US.items()):
        if col.button(label, key=f"us_irr_quick_{label}"):
            st.session_state["us_irr_threshold_slider"] = value
            st.session_state["us_irr_threshold_input"] = value

    irr_threshold_value = synced_slider(
        "預期報酬率門檻（%，不限=拉到最左）", "us_irr_threshold", IRR_SLIDER_MIN, IRR_SLIDER_MAX, 1.0,
        container=st,
    )

st.sidebar.divider()

# ---------------------------------------------------------------------------
# 側邊欄：③ 產業類別
# ---------------------------------------------------------------------------
st.sidebar.header("③ 產業類別（SECTOR）")
st.sidebar.caption(
    "預設全選；產業本身無法自動判斷是否「不易變」，請自行判斷。"
    "美股原始 SECTOR 有 200 多種英文分類，已加上中文翻譯並歸成大分類，"
    "先選「產業大分類」縮小範圍，再從下方細分產業清單挑選會更好選。"
)

us_group_keys = list(US_SECTOR_GROUPS.keys())
if st.session_state["us_sector_groups"] is None:
    st.session_state["us_sector_groups"] = list(us_group_keys)

selected_sector_groups = st.sidebar.multiselect(
    "產業大分類",
    options=us_group_keys,
    format_func=format_group_option,
    key="us_sector_groups",
)

sectors_in_groups = sorted(
    [s for s in all_sectors if us_group_of(s) in selected_sector_groups],
    key=us_translate,
)

if st.session_state["us_sectors"] is None:
    st.session_state["us_sectors"] = list(sectors_in_groups)
else:
    # 大分類縮小範圍後，先前選的細分產業若已不在範圍內就移除，
    # 避免 multiselect 的 value 超出 options 而噴錯。
    st.session_state["us_sectors"] = [s for s in st.session_state["us_sectors"] if s in sectors_in_groups]

if not selected_sector_groups:
    st.sidebar.caption("⚠️ 尚未選擇任何產業大分類，下方細分產業清單為空、篩選結果將是 0 家。")

selected_sectors = st.sidebar.multiselect(
    "細分產業（中文／English）", options=sectors_in_groups, format_func=format_sector_option, key="us_sectors"
)

st.sidebar.divider()

# ---------------------------------------------------------------------------
# 側邊欄：財報幣別（美股專屬，因跨國掛牌／ADR 幣別不一）
# ---------------------------------------------------------------------------
st.sidebar.header("財報幣別")
st.sidebar.caption(CURRENCY_CAVEAT_NOTE)
selected_currencies = st.sidebar.multiselect(
    "選擇財報幣別", options=all_currencies, key="us_currencies"
)

st.sidebar.divider()

# ---------------------------------------------------------------------------
# 側邊欄：加分項 — 估價區間（非五點原則本身，預設收合）
# ---------------------------------------------------------------------------
with st.sidebar.expander("💰 加分：估價區間篩選", expanded=False):
    valuation_mode = st.radio(
        "目前價格區間",
        options=["any", "cheap", "fair", "expensive"],
        format_func=lambda m: {
            "any": "不限",
            "cheap": "便宜價（收盤價 ≤ 淑價）",
            "fair": "合理價（淑價 ~ 貴價之間）",
            "expensive": "昂貴價（收盤價 ≥ 貴價）",
        }[m],
        key="us_valuation_mode",
    )

st.sidebar.divider()
if st.sidebar.button("🔄 清空所有篩選", key="us_clear_filters_btn"):
    st.session_state["_us_clear_filters_pending"] = True
    st.rerun()

# ---------------------------------------------------------------------------
# 套用篩選
# ---------------------------------------------------------------------------
sectors_for_filter = None if set(selected_sectors) == set(all_sectors) else selected_sectors
currencies_for_filter = None if set(selected_currencies) == set(all_currencies) else selected_currencies
irr_threshold_for_filter = None if irr_threshold_value <= IRR_SLIDER_MIN else irr_threshold_value

filter_params = {
    "roe_threshold": roe_threshold,
    "roe_mode": roe_mode,
    "payout_threshold": payout_threshold,
    "net_income_threshold": net_income_threshold,
    "sectors": sectors_for_filter,
    "valuation_mode": valuation_mode,
    "irr_threshold": irr_threshold_for_filter,
}
result_df = apply_all_filters(df, filter_params)
# filter_by_sector() 把「空 list」視為不限（沿用既有共用邏輯），但這裡的產業大分類
# 是刻意兩層式設計：使用者把大分類全部拿掉、細分產業選項變空，
# 就是明確表達「什麼產業都不要」，因此在畫面層另外補上這個 0 家的情況。
if sectors_for_filter == []:
    result_df = result_df.iloc[0:0]
if currencies_for_filter is not None:
    result_df = result_df[result_df["財報幣別"].isin(currencies_for_filter)]

# ---------------------------------------------------------------------------
# 主畫面：標題與已知限制
# ---------------------------------------------------------------------------
st.title("🗽 巴爺爺選股 — 美股｜五點好企業原則篩選系統")
st.markdown('<div id="us-page-top"></div>', unsafe_allow_html=True)
with st.expander("⚠️ 已知限制（請詳閱）", expanded=False):
    st.markdown(
        f"""
- 本系統**只能自動判斷五點原則中的 ①②④（淨利部分）**，共 {COVERAGE_AUTO_ITEMS}/{COVERAGE_TOTAL} 項。
- ③（不會變的公司）僅提供產業分類供人工判斷；④（上市滿 2 年）與 ⑤（董監持股 ≥10%）**完全無法自動判斷**，
  須自行至 [SEC EDGAR](https://www.sec.gov/edgar/search/) 或 Yahoo Finance 等公開資料源查證。
- {CURRENCY_CAVEAT_NOTE}
- 資料為單一時間點快照（資料日期：**{data_date}**），非即時更新，請注意資料新舊。
- {MANUAL_CHECK_NOTE_US}
        """
    )

# ---------------------------------------------------------------------------
# 主畫面：快速查詢／篩選結果分頁
#
# 兩者分開放在不同分頁，是因為快速查詢一旦選到股票就會展開一整張詳細卡片
# （圖表＋檢核清單＋同業比較表），如果和篩選結果放在同一個直向捲動頁面裡，
# 篩選結果會被這張卡片往下推、使用者要多滑很多才看得到，體驗很差。
# 分頁可以讓兩種使用情境（「我要查一檔特定股票」vs「我要瀏覽篩選出的清單」）
# 各自佔一個獨立畫面，互不干擾。
# ---------------------------------------------------------------------------
tab_search, tab_screen = st.tabs(["🔍 快速查詢股票", "📊 篩選結果與個股詳情"])

with tab_search:
    st.caption("輸入股票代號或公司名稱（支援部分比對，僅比對英文原文），可直接看到該股票的資料，不受篩選條件影響。")
    us_search_query = st.text_input(
        "股票代號或名稱", key="us_search_query", placeholder="例如：AAPL 或 Apple",
        label_visibility="collapsed",
    )
    if us_search_query.strip():
        q = us_search_query.strip()
        search_mask = (
            df["Symbol"].str.contains(q, case=False, na=False, regex=False)
            | df["COMPANY"].str.contains(q, case=False, na=False, regex=False)
        )
        search_matches = df[search_mask]
        if len(search_matches) == 0:
            st.warning(f"找不到符合「{q}」的股票，請確認代號或名稱是否正確。")
        else:
            if len(search_matches) > 30:
                st.caption(f"找到 {len(search_matches)} 檔符合，僅顯示前 30 筆，請輸入更精確的關鍵字以縮小範圍。")
                search_matches = search_matches.head(30)
            search_options = (search_matches["Symbol"] + "　" + search_matches["COMPANY"]).tolist()
            search_picked = st.selectbox(
                f"找到 {len(search_matches)} 檔符合「{q}」，請選擇要查看的股票：",
                options=search_options, key="us_search_pick",
            )
            if search_picked:
                search_symbol = search_picked.split("　")[0]
                search_row = df[df["Symbol"] == search_symbol].iloc[0]
                render_stock_detail(search_row, df, roe_threshold, key_prefix="us_search")

with tab_screen:
    # -----------------------------------------------------------------
    # 指標卡
    # -----------------------------------------------------------------
    metric_cols = st.columns(3)
    avg_roe = result_df["預期ROE"].mean() if len(result_df) else float("nan")
    metric_values = [
        ("符合條件家數", f"{len(result_df):,}"),
        ("資料總家數", f"{len(df):,}"),
        ("符合結果平均預期ROE", f"{avg_roe:.2f}%" if pd.notna(avg_roe) else "—"),
    ]
    for col, (label, value) in zip(metric_cols, metric_values):
        with col, st.container(border=True):
            st.metric(label, value)

    st.divider()

    # -----------------------------------------------------------------
    # 結果表格
    # -----------------------------------------------------------------
    st.subheader("篩選結果")

    if len(result_df) == 0:
        st.info("目前條件下沒有符合的股票，請調整篩選條件。")
    else:
        display_df = result_df.copy()
        display_df["五點覆蓋度"] = display_df.apply(compute_coverage_score, axis=1)
        # 5年ROE直接展開成 5 個數字欄位（而非小圖表），方便一眼比較每年數字
        roe_year_cols = [f"ROE({label})" for label in ROE_YEAR_LABELS_OLD_TO_NEW]
        display_df[roe_year_cols] = display_df[list(reversed(ROE_COLS_RECENT_TO_OLD))]

        display_df["估價區間"] = valuation_labels(display_df)
        display_df["產業(中文)"] = display_df["SECTOR"].apply(
            lambda s: us_translate(s) if pd.notna(s) else s
        )

        show_cols = {
            "Symbol": "股票代號",
            "COMPANY": "公司名稱",
            "COUNTRY": "國家",
            "產業(中文)": "產業(中文)",
            "SECTOR": "產業(English)",
            "Industry": "細分產業(Industry)",
            "財報幣別": "財報幣別",
            "市值($m)": "市值($M)",
            "預期ROE": "預期ROE(%)",
            **{c: c for c in roe_year_cols},
            "預期配息率": "配息率(%)",
            "預期常利": "淨利(百萬,原幣)",
            "估價區間": "估價區間",
            "預期報酬率": "預期報酬率IRR(%)",
            "五點覆蓋度": "五點覆蓋度",
        }
        table = display_df[list(show_cols.keys())].rename(columns=show_cols)

        st.caption("💡 點擊表格中任一列可直接跳到下方「個股詳細檢視」。")
        table_event = st.dataframe(
            table,
            width="stretch",
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="us_results_table_select",
            column_config={
                "市值($M)": st.column_config.NumberColumn(format="%.1f"),
                "預期ROE(%)": st.column_config.NumberColumn(format="%.2f"),
                **{c: st.column_config.NumberColumn(format="%.1f") for c in roe_year_cols},
                "配息率(%)": st.column_config.NumberColumn(format="%.2f"),
                "淨利(百萬,原幣)": st.column_config.NumberColumn(format="%.1f"),
                "預期報酬率IRR(%)": st.column_config.NumberColumn(format="%.1f"),
            },
        )
        selected_rows = table_event.selection.rows if table_event and table_event.selection else []
        if selected_rows:
            st.session_state["us_detail_symbol"] = result_df.iloc[selected_rows[0]]["Symbol"]
            st.session_state["_us_scroll_to_detail"] = True

        # -------------------------------------------------------------
        # 下載按鈕
        #
        # table 現在每欄都已經是純量值（5年ROE已展開成獨立數字欄位），
        # CSV／Excel 直接共用同一份表格即可，欄位自然一致。
        # -------------------------------------------------------------
        dl_cols = st.columns(2)
        dl_cols[0].download_button(
            "⬇️ 下載 CSV", data=_to_csv_bytes(table), file_name="us_screener_result.csv", mime="text/csv",
            key="us_dl_csv",
        )
        dl_cols[1].download_button(
            "⬇️ 下載 Excel",
            data=_to_excel_bytes(table),
            file_name="us_screener_result.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="us_dl_xlsx",
        )

        st.divider()

        # -------------------------------------------------------------
        # 詳細卡片
        # -------------------------------------------------------------
        st.markdown('<div id="us-detail-section"></div>', unsafe_allow_html=True)
        st.subheader("個股詳細檢視")

        if st.session_state.pop("_us_scroll_to_detail", False):
            components.html(
                """
                <script>
                    setTimeout(function () {
                        const doc = window.parent.document;
                        const el = doc.getElementById('us-detail-section');
                        if (el) { el.scrollIntoView({behavior: 'smooth', block: 'start'}); }
                    }, 150);
                </script>
                """,
                height=0,
            )
        symbol_options = (result_df["Symbol"] + "　" + result_df["COMPANY"]).tolist()

        # 刻意不對這個 selectbox 使用 key（見 views/tw.py 同一位置的詳細註解）：
        # 一旦加上 key，Streamlit 會把 key 當成 widget 唯一身分、之後每次
        # rerun 都忽略 index=，導致「點表格列 → 跳到該股票」完全失效。
        current_symbol = st.session_state.get("us_detail_symbol")
        current_label = next((lbl for lbl in symbol_options if lbl.startswith(f"{current_symbol}　")), None)
        default_index = symbol_options.index(current_label) if current_label else 0

        picked = st.selectbox(
            "選擇股票查看詳情（或直接點擊上方表格列）", options=symbol_options, index=default_index,
        )

        if picked:
            picked_symbol = picked.split("　")[0]
            st.session_state["us_detail_symbol"] = picked_symbol
            row = result_df[result_df["Symbol"] == picked_symbol].iloc[0]
            render_stock_detail(row, df, roe_threshold, key_prefix="us")
