# -*- coding: utf-8 -*-
"""
巴爺爺選股 — 台股頁面（五點好企業原則篩選系統）
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
    DEFAULT_IRR_THRESHOLD,
    DEFAULT_MARKET_CAP_THRESHOLD,
    DEFAULT_PAYOUT_THRESHOLD,
    DEFAULT_ROE_THRESHOLD,
    IRR_QUICK_OPTIONS,
    IRR_SLIDER_MAX,
    IRR_SLIDER_MIN,
    MANUAL_CHECK_NOTE,
    MOPS_URL_TEMPLATE,
    NET_INCOME_QUICK_OPTIONS,
    PAYOUT_QUICK_OPTIONS,
    ROE_COLS_RECENT_TO_OLD,
    ROE_YEAR_LABELS_OLD_TO_NEW,
)
from src.data_loader import DataLoadError, get_data_date, load_tw_data
from src.scoring import compute_coverage_score, compute_roe_stability
from src.screener import apply_all_filters, filter_by_roe, valuation_labels
from src.tw_sector_groups import TW_SECTOR_GROUPS
from src.tw_sector_groups import group_of as tw_group_of
from src.ui_helpers import synced_slider

DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "twlist.xlsx"
)


# ---------------------------------------------------------------------------
# 資料載入（含快取）
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="讀取資料中…")
def _load_from_path(path: str, mtime: float) -> pd.DataFrame:
    return load_tw_data(path)


@st.cache_data(show_spinner="讀取資料中…")
def _load_from_bytes(file_bytes: bytes) -> pd.DataFrame:
    return load_tw_data(io.BytesIO(file_bytes))


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
        "tw_roe_threshold_slider": 0.0,
        "tw_roe_threshold_input": 0.0,
        "tw_payout_threshold_slider": 0.0,
        "tw_payout_threshold_input": 0.0,
        "tw_net_income_threshold": 0.0,
        "tw_sector_groups": None,  # None 代表尚未依資料初始化
        "tw_sectors": None,  # None 代表尚未依資料初始化
        "tw_valuation_mode": "any",
        "tw_irr_threshold_slider": IRR_SLIDER_MIN,
        "tw_irr_threshold_input": IRR_SLIDER_MIN,
        "tw_detail_symbol": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def clear_all_filters(all_sectors):
    """
    重設所有篩選條件，包含已實例化的 widget key。

    注意：Streamlit 不允許在一個 widget 已於本次 script run 建立之後，
    再修改其對應的 session_state key。因此這個函式必須在任何側邊欄
    widget 建立「之前」呼叫（見下方 `_clear_filters_pending` 的處理方式），
    不能直接掛在按鈕的 on_click 之後、其餘 widget 都已建立完的位置呼叫。
    """
    st.session_state["tw_roe_threshold_slider"] = 0.0
    st.session_state["tw_roe_threshold_input"] = 0.0
    st.session_state["tw_payout_threshold_slider"] = 0.0
    st.session_state["tw_payout_threshold_input"] = 0.0
    st.session_state["tw_net_income_threshold"] = 0.0
    st.session_state["tw_sector_groups"] = list(TW_SECTOR_GROUPS.keys())
    st.session_state["tw_sectors"] = list(all_sectors)
    st.session_state["tw_valuation_mode"] = "any"
    st.session_state["tw_irr_threshold_slider"] = IRR_SLIDER_MIN
    st.session_state["tw_irr_threshold_input"] = IRR_SLIDER_MIN


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
        payout_ok = row["預期配息率"] >= DEFAULT_PAYOUT_THRESHOLD
        market_cap_ok = None if pd.isna(row["市值(億)"]) else row["市值(億)"] >= DEFAULT_MARKET_CAP_THRESHOLD

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
            f"（課程門檻 {DEFAULT_PAYOUT_THRESHOLD}%），盈再率 {retention_text}"
        )
        st.markdown(f"- ⚠️ ③不會變的公司：產業別「{row['SECTOR']}」，請自行判斷")
        market_cap_text = "—（無資料）" if pd.isna(row["市值(億)"]) else f"{row['市值(億)']:.1f} 億元"
        st.markdown(
            f"- {mark(market_cap_ok)} ④公司夠大：市值 {market_cap_text}"
            f"（門檻 {DEFAULT_MARKET_CAP_THRESHOLD:.0f} 億元），上市年資 ❌ 待查證"
        )
        st.markdown("- ❌ ⑤老闆誠信：董監持股 待查證")

        irr_text = "—（無法估算）" if pd.isna(row["預期報酬率"]) else f"{row['預期報酬率']:.1f}%"
        irr_ok = None if pd.isna(row["預期報酬率"]) else row["預期報酬率"] >= DEFAULT_IRR_THRESHOLD
        st.markdown(
            f"- {mark(irr_ok)} 延伸判準：預期報酬率(IRR) {irr_text}"
            f"（課程門檻 ≥{DEFAULT_IRR_THRESHOLD:.0f}%）"
        )

        mops_url = MOPS_URL_TEMPLATE.format(symbol=row["Symbol"])
        st.link_button("前往公開資訊觀測站查證 ④⑤", mops_url, key=f"{key_prefix}_mops_link")

    st.divider()
    if pd.isna(row["SECTOR"]):
        st.caption("此公司無產業分類資料，無法進行同業比較。")
    else:
        with st.container(border=True):
            peers = df[df["SECTOR"] == row["SECTOR"]].copy()
            peers = peers.sort_values("市值(億)", ascending=False, na_position="last").reset_index(drop=True)
            peers.insert(0, "排名", peers.index + 1)
            peers["淨利(億)"] = peers["預期常利"] / 100.0
            peers["本股"] = peers["Symbol"].apply(lambda s: "👉" if s == row["Symbol"] else "")

            my_rank_rows = peers.index[peers["Symbol"] == row["Symbol"]]
            my_rank = int(my_rank_rows[0]) + 1 if len(my_rank_rows) else None
            total_peers = len(peers)

            st.markdown(f"**同業比較 — {row['SECTOR']}（共 {total_peers} 家，依市值排序）**")
            if my_rank and pd.notna(row["市值(億)"]):
                st.caption(f"{row['COMPANY']} 市值約 {row['市值(億)']:.1f} 億元，同業市值排名第 {my_rank}/{total_peers} 名")

            peer_show_cols = {
                "本股": "本股",
                "排名": "排名",
                "Symbol": "股票代號",
                "COMPANY": "公司名稱",
                "市值(億)": "市值(億)",
                "預期ROE": "預期ROE(%)",
                "預期配息率": "配息率(%)",
                "淨利(億)": "淨利(億)",
            }
            peer_table = peers[list(peer_show_cols.keys())].rename(columns=peer_show_cols)
            st.dataframe(
                peer_table,
                width="stretch",
                hide_index=True,
                height=350,
                key=f"{key_prefix}_peer_table",
                column_config={
                    "市值(億)": st.column_config.NumberColumn(format="%.1f"),
                    "預期ROE(%)": st.column_config.NumberColumn(format="%.2f"),
                    "配息率(%)": st.column_config.NumberColumn(format="%.2f"),
                    "淨利(億)": st.column_config.NumberColumn(format="%.2f"),
                },
            )

    st.markdown("[⬆️ 回到最上方](#tw-page-top)")


init_session_defaults()

# ---------------------------------------------------------------------------
# 側邊欄：資料來源
# ---------------------------------------------------------------------------
st.sidebar.header("📁 資料來源（台股）")
uploaded_file = st.sidebar.file_uploader("上傳最新股票清單 Excel", type=["xlsx"], key="tw_uploader")

try:
    if uploaded_file is not None:
        df = _load_from_bytes(uploaded_file.getvalue())
        source_label = f"上傳檔案：{uploaded_file.name}"
    else:
        if not os.path.exists(DATA_PATH):
            st.error(f"找不到預設資料檔：{DATA_PATH}，請於側邊欄上傳 Excel 檔案。")
            st.stop()
        df = _load_from_path(DATA_PATH, os.path.getmtime(DATA_PATH))
        source_label = "預設資料：data/twlist.xlsx"
except DataLoadError as exc:
    st.error(f"資料讀取失敗：{exc}")
    st.stop()

data_date = get_data_date(df)
st.sidebar.caption(f"目前資料來源：{source_label}")
st.sidebar.caption(f"資料日期（收盤日）：{data_date}")

# 市值(億) = 收盤價 × Shares（Shares 欄位單位為百萬股，故收盤價×Shares＝市值百萬元，再除以100轉億元）
df = df.assign(**{"市值(億)": df["收盤價"] * df["Shares"] / 100.0})

all_sectors = sorted(df["SECTOR"].dropna().unique().tolist())

# 「清空所有篩選」必須在任何篩選 widget 建立之前套用，見 clear_all_filters() 註解
if st.session_state.get("_tw_clear_filters_pending"):
    clear_all_filters(all_sectors)
    st.session_state["_tw_clear_filters_pending"] = False

st.sidebar.divider()

# ---------------------------------------------------------------------------
# 側邊欄：① ROE 穩定度篩選
# ---------------------------------------------------------------------------
st.sidebar.header("① ROE 穩定度篩選")
st.sidebar.caption(
    f"近5年（ROE1~ROE5 實際歷史值，非預期ROE）任一年低於門檻就排除，"
    f"缺值視為不通過。門檻設為 0 代表不限。（課程門檻參考值：{DEFAULT_ROE_THRESHOLD:.0f}%）"
)

roe_threshold = synced_slider("ROE 門檻（%，0=不限）", "tw_roe_threshold", 0.0, 40.0, 0.5)
st.sidebar.caption(f"目前門檻下符合 {len(filter_by_roe(df, roe_threshold)):,} 家")

st.sidebar.divider()

# ---------------------------------------------------------------------------
# 側邊欄：② 配息率篩選
# ---------------------------------------------------------------------------
st.sidebar.header("② 配息率篩選")
payout_cols = st.sidebar.columns(len(PAYOUT_QUICK_OPTIONS))
for col, (label, value) in zip(payout_cols, PAYOUT_QUICK_OPTIONS.items()):
    if col.button(label, key=f"tw_payout_quick_{label}"):
        st.session_state["tw_payout_threshold_slider"] = value
        st.session_state["tw_payout_threshold_input"] = value

payout_threshold = synced_slider("配息率門檻（%，0=不限）", "tw_payout_threshold", 0.0, 100.0, 1.0)

st.sidebar.divider()

# ---------------------------------------------------------------------------
# 側邊欄：④ 淨利門檻
# ---------------------------------------------------------------------------
st.sidebar.header("④ 淨利門檻（公司夠大）")
net_income_cols = st.sidebar.columns(len(NET_INCOME_QUICK_OPTIONS))
for col, (label, value) in zip(net_income_cols, NET_INCOME_QUICK_OPTIONS.items()):
    if col.button(label, key=f"tw_ni_quick_{label}"):
        st.session_state["tw_net_income_threshold"] = value

net_income_threshold = st.sidebar.number_input(
    "淨利門檻（百萬元，0=不限）", min_value=0.0, step=50.0, key="tw_net_income_threshold"
)

st.sidebar.caption("「上市櫃滿 2 年」資料中無此欄位，不做篩選，請自行至公開資訊觀測站查證。")
st.sidebar.divider()

# ---------------------------------------------------------------------------
# 側邊欄：延伸判準 — 預期報酬率（IRR）（非五點原則本身，預設收合）
# ---------------------------------------------------------------------------
with st.sidebar.expander("🎯 延伸判準：預期報酬率（IRR）", expanded=False):
    st.caption(
        f"對應課程 Ch6「合理買價報酬率」概念，課程延伸判準為 IRR ≥ {DEFAULT_IRR_THRESHOLD:.0f}%。"
        "滑到最左（不限）時不套用；套用時，無法估算 IRR 的公司會被排除。"
    )
    irr_cols = st.columns(len(IRR_QUICK_OPTIONS))
    for col, (label, value) in zip(irr_cols, IRR_QUICK_OPTIONS.items()):
        if col.button(label, key=f"tw_irr_quick_{label}"):
            st.session_state["tw_irr_threshold_slider"] = value
            st.session_state["tw_irr_threshold_input"] = value

    irr_threshold_value = synced_slider(
        "預期報酬率門檻（%，不限=拉到最左）", "tw_irr_threshold", IRR_SLIDER_MIN, IRR_SLIDER_MAX, 1.0,
        container=st,
    )

st.sidebar.divider()

# ---------------------------------------------------------------------------
# 側邊欄：③ 產業類別
# ---------------------------------------------------------------------------
st.sidebar.header("③ 產業類別（SECTOR）")
st.sidebar.caption(
    "預設全選；產業本身無法自動判斷是否「不易變」，請自行判斷。"
    "先選「產業大分類」縮小範圍，再從下方細分產業清單挑選會更好選。"
)

tw_group_keys = list(TW_SECTOR_GROUPS.keys())
if st.session_state["tw_sector_groups"] is None:
    st.session_state["tw_sector_groups"] = list(tw_group_keys)

selected_sector_groups = st.sidebar.multiselect(
    "產業大分類",
    options=tw_group_keys,
    format_func=lambda g: TW_SECTOR_GROUPS[g],
    key="tw_sector_groups",
)

sectors_in_groups = sorted([s for s in all_sectors if tw_group_of(s) in selected_sector_groups])

if st.session_state["tw_sectors"] is None:
    st.session_state["tw_sectors"] = list(sectors_in_groups)
else:
    # 大分類縮小範圍後，先前選的細分產業若已不在範圍內就移除，
    # 避免 multiselect 的 value 超出 options 而噴錯。
    st.session_state["tw_sectors"] = [s for s in st.session_state["tw_sectors"] if s in sectors_in_groups]

if not selected_sector_groups:
    st.sidebar.caption("⚠️ 尚未選擇任何產業大分類，下方細分產業清單為空、篩選結果將是 0 家。")

selected_sectors = st.sidebar.multiselect(
    "細分產業", options=sectors_in_groups, key="tw_sectors"
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
        key="tw_valuation_mode",
    )

st.sidebar.divider()
if st.sidebar.button("🔄 清空所有篩選", key="tw_clear_filters_btn"):
    st.session_state["_tw_clear_filters_pending"] = True
    st.rerun()

# ---------------------------------------------------------------------------
# 套用篩選
# ---------------------------------------------------------------------------
# 全選（未實際縮小範圍）時視為不篩選，讓沒有 SECTOR 資料的公司仍會出現在預設結果中
sectors_for_filter = None if set(selected_sectors) == set(all_sectors) else selected_sectors
# 滑到最左（下界）視為不限，避免排除掉沒有 IRR 資料的公司
irr_threshold_for_filter = None if irr_threshold_value <= IRR_SLIDER_MIN else irr_threshold_value

filter_params = {
    "roe_threshold": roe_threshold,
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

# ---------------------------------------------------------------------------
# 主畫面：標題與已知限制
# ---------------------------------------------------------------------------
st.title("🐢 巴爺爺選股 — 台股｜五點好企業原則篩選系統")
st.markdown('<div id="tw-page-top"></div>', unsafe_allow_html=True)
with st.expander("⚠️ 已知限制（請詳閱）", expanded=False):
    st.markdown(
        f"""
- 本系統**只能自動判斷五點原則中的 ①②④（淨利部分）**，共 {COVERAGE_AUTO_ITEMS}/{COVERAGE_TOTAL} 項。
- ③（不會變的公司）僅提供產業分類供人工判斷；④（上市滿 2 年）與 ⑤（董監持股 ≥10%）**完全無法自動判斷**，
  須自行至[公開資訊觀測站](https://mops.twse.com.tw)或 GoodInfo 查證。
- 資料為單一時間點快照（資料日期：**{data_date}**），非即時更新，請注意資料新舊。
- {MANUAL_CHECK_NOTE}
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
    st.caption("輸入股票代號或公司名稱（支援部分比對），可直接看到該股票的資料，不受篩選條件影響。")
    tw_search_query = st.text_input(
        "股票代號或名稱", key="tw_search_query", placeholder="例如：2330 或 台積電",
        label_visibility="collapsed",
    )
    if tw_search_query.strip():
        q = tw_search_query.strip()
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
                options=search_options, key="tw_search_pick",
            )
            if search_picked:
                search_symbol = search_picked.split("　")[0]
                search_row = df[df["Symbol"] == search_symbol].iloc[0]
                render_stock_detail(search_row, df, roe_threshold, key_prefix="tw_search")

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
        display_df["淨利(億)"] = display_df["預期常利"] / 100.0
        display_df["五點覆蓋度"] = display_df.apply(compute_coverage_score, axis=1)
        # 5年ROE直接展開成 5 個數字欄位（而非小圖表），方便一眼比較每年數字
        roe_year_cols = [f"ROE({label})" for label in ROE_YEAR_LABELS_OLD_TO_NEW]
        display_df[roe_year_cols] = display_df[list(reversed(ROE_COLS_RECENT_TO_OLD))]

        display_df["估價區間"] = valuation_labels(display_df)

        show_cols = {
            "Symbol": "股票代號",
            "COMPANY": "公司名稱",
            "SECTOR": "產業",
            "市值(億)": "市值(億)",
            "預期ROE": "預期ROE(%)",
            **{c: c for c in roe_year_cols},
            "預期配息率": "配息率(%)",
            "淨利(億)": "淨利(億)",
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
            key="tw_results_table_select",
            column_config={
                "市值(億)": st.column_config.NumberColumn(format="%.1f"),
                "預期ROE(%)": st.column_config.NumberColumn(format="%.2f"),
                **{c: st.column_config.NumberColumn(format="%.1f") for c in roe_year_cols},
                "配息率(%)": st.column_config.NumberColumn(format="%.2f"),
                "淨利(億)": st.column_config.NumberColumn(format="%.2f"),
                "預期報酬率IRR(%)": st.column_config.NumberColumn(format="%.1f"),
            },
        )
        selected_rows = table_event.selection.rows if table_event and table_event.selection else []
        if selected_rows:
            st.session_state["tw_detail_symbol"] = result_df.iloc[selected_rows[0]]["Symbol"]
            st.session_state["_tw_scroll_to_detail"] = True

        # -------------------------------------------------------------
        # 下載按鈕
        #
        # table 現在每欄都已經是純量值（5年ROE已展開成獨立數字欄位），
        # CSV／Excel 直接共用同一份表格即可，欄位自然一致。
        # -------------------------------------------------------------
        dl_cols = st.columns(2)
        dl_cols[0].download_button(
            "⬇️ 下載 CSV", data=_to_csv_bytes(table), file_name="tw_screener_result.csv", mime="text/csv",
            key="tw_dl_csv",
        )
        dl_cols[1].download_button(
            "⬇️ 下載 Excel",
            data=_to_excel_bytes(table),
            file_name="tw_screener_result.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="tw_dl_xlsx",
        )

        st.divider()

        # -------------------------------------------------------------
        # 詳細卡片
        # -------------------------------------------------------------
        st.markdown('<div id="tw-detail-section"></div>', unsafe_allow_html=True)
        st.subheader("個股詳細檢視")

        if st.session_state.pop("_tw_scroll_to_detail", False):
            # st.dataframe 點選只會更新內部狀態，畫面不會自動捲動，
            # 這裡用一小段注入的 JS 把主畫面（父層 iframe）捲到詳細檢視區塊，
            # 讓「點表格→跳到該股票資訊」真的看得到「跳過去」的效果。
            components.html(
                """
                <script>
                    setTimeout(function () {
                        const doc = window.parent.document;
                        const el = doc.getElementById('tw-detail-section');
                        if (el) { el.scrollIntoView({behavior: 'smooth', block: 'start'}); }
                    }, 150);
                </script>
                """,
                height=0,
            )
        symbol_options = (result_df["Symbol"] + "　" + result_df["COMPANY"]).tolist()

        # 決定下拉選單預設值：優先採用「表格點擊」或前一次選擇記住的股票，
        # 若該股票已被目前篩選條件排除，則退回第一筆。這裡刻意不對 selectbox
        # 使用 key（不要加 key= 參數！），而是每次執行時用 index= 計算出的
        # 「衍生值」帶入，並在下面把使用者手動選擇的結果寫回 session_state。
        # 一旦加上 key，Streamlit（≥1.49，key_as_main_identity 機制）會把
        # key 當成這個 widget 的唯一身分、之後每次 rerun 都忽略 index=，
        # 導致「點表格列 → 更新 tw_detail_symbol → 想帶動下拉選單跳過去」
        # 完全失效（曾經真的這樣壞過一次，見 commit 歷史），選單會卡在
        # 使用者上一次手動選的股票，點表格列變成沒有反應。
        current_symbol = st.session_state.get("tw_detail_symbol")
        current_label = next((lbl for lbl in symbol_options if lbl.startswith(f"{current_symbol}　")), None)
        default_index = symbol_options.index(current_label) if current_label else 0

        picked = st.selectbox(
            "選擇股票查看詳情（或直接點擊上方表格列）", options=symbol_options, index=default_index,
        )

        if picked:
            picked_symbol = picked.split("　")[0]
            st.session_state["tw_detail_symbol"] = picked_symbol
            row = result_df[result_df["Symbol"] == picked_symbol].iloc[0]
            render_stock_detail(row, df, roe_threshold, key_prefix="tw")
