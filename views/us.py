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
import streamlit as st

from src.constants import (
    COVERAGE_AUTO_ITEMS,
    COVERAGE_TOTAL,
    CURRENCY_CAVEAT_NOTE,
    DEFAULT_IRR_THRESHOLD_US,
    DEFAULT_MARKET_CAP_THRESHOLD_US,
    DEFAULT_NET_INCOME_THRESHOLD_US,
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
from src.detail_card import DetailCardSpec, render_stock_detail
from src.scoring import compute_coverage_score
from src.screener import (
    ROE_FILTER_MODE_LABELS,
    ROE_FILTER_MODES,
    apply_all_filters,
    filter_by_roe,
    valuation_labels,
)
from src.ui_helpers import (
    init_two_level_sector_state,
    render_download_buttons,
    scroll_to_anchor,
    sync_two_level_sector_state,
    synced_slider,
)
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

# 個股詳細卡片市場專屬設定（見 src/detail_card.py 的 DetailCardSpec、
# render_stock_detail()：兩個市場共用同一份渲染邏輯，這裡只放「真正不同」
# 的部分，例如市值欄位命名、門檻數字、查證連結、同業比較分組依據）。
#
# market_cap_value_fmt／peer 表頭的市值文字原本分別寫成「USD {v:.1f}M」與
# 「{v:.1f} 百萬美元」兩種不同措辭（同一支 render_stock_detail() 裡就不一致），
# 統一成共用函式後兩處自然變成同一套措辭（USD 格式），純文字表達方式調整，
# 數字與判斷邏輯不受影響。
US_DETAIL_CARD_SPEC = DetailCardSpec(
    market_cap_col="市值($m)",
    market_cap_display_label="市值($M)",
    market_cap_threshold=DEFAULT_MARKET_CAP_THRESHOLD_US,
    market_cap_value_fmt=lambda v: f"USD {v:.1f}M",
    market_cap_threshold_fmt=lambda v: f"USD {v:.0f}M",
    irr_threshold=DEFAULT_IRR_THRESHOLD_US,
    verify_url_template=YAHOO_FINANCE_URL_TEMPLATE,
    verify_button_label="前往 Yahoo Finance 查證 ④⑤",
    peer_group_col="Industry",
    peer_missing_caption="此公司無細分產業（Industry）資料，無法進行同業比較。",
    peer_header_fn=lambda row, total: f"{row['Industry']}（Industry，共 {total} 家，依市值排序）",
    sector_check_text_fn=lambda row: (
        f"Sector「{us_translate(row['SECTOR'])}（{row['SECTOR']}）」／"
        f"Industry「{row['Industry'] if pd.notna(row['Industry']) else '—'}」"
    ) if pd.notna(row["SECTOR"]) else (
        f"Sector「—」／Industry「{row['Industry'] if pd.notna(row['Industry']) else '—'}」"
    ),
    ownership_check_label="內部人（董監）持股",
    # 營收與淨利一樣是各公司原始財報幣別的數值，故標註「財報幣別」。
    revenue_unit_fn=lambda row: f"百萬（{row['財報幣別']}）" if pd.notna(row.get("財報幣別")) else "百萬",
    peer_extra_column_builder=lambda peers: peers,  # 財報幣別／預期常利已是原始欄位，不需額外計算
    peer_extra_show_cols={"財報幣別": "財報幣別", "預期常利": "淨利(百萬,原幣)"},
    peer_extra_column_config={"淨利(百萬,原幣)": st.column_config.NumberColumn(format="%.1f")},
    page_top_anchor="us-page-top",
)


# ---------------------------------------------------------------------------
# 資料載入（含快取）
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="讀取資料中…", max_entries=2)
def _load_from_path(path: str, mtime: float) -> pd.DataFrame:
    return load_us_data(path)


@st.cache_data(show_spinner="讀取資料中…", max_entries=2)
def _load_from_bytes(file_bytes: bytes) -> pd.DataFrame:
    return load_us_data(io.BytesIO(file_bytes))


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
        "_us_prev_sector_groups": None,  # 用於偵測「新勾選的大分類」，見下方細分產業還原邏輯
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
    st.session_state["_us_prev_sector_groups"] = list(US_SECTOR_GROUPS.keys())
    st.session_state["us_currencies"] = list(all_currencies)
    st.session_state["us_valuation_mode"] = "any"
    st.session_state["us_irr_threshold_slider"] = IRR_SLIDER_MIN
    st.session_state["us_irr_threshold_input"] = IRR_SLIDER_MIN


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
init_two_level_sector_state("us_sector_groups", "us_sectors", "_us_prev_sector_groups", us_group_keys)

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
# 大分類縮小範圍後，先前選的細分產業若已不在範圍內就移除；大分類「新增」範圍
# 時，新出現的細分產業預設一併勾選。細節與修正前的 bug 見
# src/ui_helpers.py 的 sync_two_level_sector_state()。
sync_two_level_sector_state(
    selected_sector_groups, "us_sectors", "_us_prev_sector_groups", sectors_in_groups, us_group_of,
    sort_key=us_translate,
)

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
                render_stock_detail(search_row, df, roe_threshold, roe_mode, payout_threshold, key_prefix="us_search", spec=US_DETAIL_CARD_SPEC)

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

        # table 現在每欄都已經是純量值（5年ROE已展開成獨立數字欄位），
        # CSV／Excel 直接共用同一份表格即可，欄位自然一致。下載按鈕邏輯
        # （含 Excel 延後產生、內容雜湊防抓到舊檔案）見 src/ui_helpers.py
        # 的 render_download_buttons()。
        render_download_buttons(table, key_prefix="us", file_stem="us_screener_result")

        st.divider()

        # -------------------------------------------------------------
        # 詳細卡片
        # -------------------------------------------------------------
        st.markdown('<div id="us-detail-section"></div>', unsafe_allow_html=True)
        st.subheader("個股詳細檢視")

        if st.session_state.pop("_us_scroll_to_detail", False):
            scroll_to_anchor("us-detail-section")
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
            render_stock_detail(row, df, roe_threshold, roe_mode, payout_threshold, key_prefix="us", spec=US_DETAIL_CARD_SPEC)
