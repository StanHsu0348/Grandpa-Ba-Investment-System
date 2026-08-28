# -*- coding: utf-8 -*-
"""
個股詳細卡片（5年 ROE 趨勢圖、五點原則逐項檢核、同業比較）的共用渲染邏輯。

台股／美股頁面的個股詳細卡片原本是各自複製一份幾乎一樣的 render_stock_detail()
（約140行，結構、檢核邏輯、圖表完全相同），只有欄位命名、門檻數字、連結網址、
同業比較的分組依據等少數地方因市場不同而不同。這正是 B6～B9 幾個 bug
（①②判準跟側邊欄篩選不一致、同業比較表缺欄位）原本的成因——兩份幾乎一樣
的程式碼，改一邊很容易忘記改另一邊。

統一成這裡的共用函式後，市場之間「真正不同」的地方（門檻數字、格式化文字、
查證連結、同業比較分組欄位…）集中放在呼叫端建立的 DetailCardSpec 裡，
渲染邏輯與檢核判準只有一份，兩個市場自動保持一致，不會再各自漂移。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .constants import ROE_COLS_RECENT_TO_OLD, ROE_YEAR_LABELS_OLD_TO_NEW
from .screener import ROE_FILTER_MODE_LABELS, roe_row_passes
from .scoring import compute_roe_stability


@dataclass(frozen=True)
class DetailCardSpec:
    """個股詳細卡片裡「因市場而異」的部分，其餘（檢核判準、圖表、排版結構）
    由 render_stock_detail() 統一處理，兩個市場共用同一份邏輯。"""

    market_cap_col: str                              # "市值(億)" 或 "市值($m)"（原始欄名）
    market_cap_display_label: str                     # 同業比較表顯示用欄名，可能與原始欄名大小寫不同
                                                        # （美股原始欄「市值($m)」顯示成「市值($M)」）
    market_cap_threshold: float                       # DEFAULT_MARKET_CAP_THRESHOLD(_US)
    market_cap_value_fmt: Callable[[float], str]       # 市值數字 -> 顯示文字，例如 "50.0 億元"
    market_cap_threshold_fmt: Callable[[float], str]   # 市值門檻 -> 顯示文字，例如 "50 億元"
    irr_threshold: float                               # DEFAULT_IRR_THRESHOLD(_US)
    verify_url_template: str                           # MOPS_URL_TEMPLATE 或 YAHOO_FINANCE_URL_TEMPLATE
    verify_button_label: str                           # 查證連結按鈕文字
    peer_group_col: str                                # 同業比較分組依據："SECTOR" 或 "Industry"
    peer_missing_caption: str                          # 分組欄位缺值時顯示的提示文字
    peer_header_fn: Callable[[pd.Series, int], str]     # (row, total_peers) -> 同業比較表頭「—」後面的文字
    sector_check_text_fn: Callable[[pd.Series], str]    # row -> ③不會變的公司 那行的內文
    ownership_check_label: str                          # ⑤老闆誠信 那行「董監持股」部分的文字
    revenue_unit_fn: Callable[[pd.Series], str]         # row -> 最近年度營收數字後面的單位文字
    peer_extra_column_builder: Callable[[pd.DataFrame], pd.DataFrame]  # 幫同業比較表加上市場專屬的計算欄位
    peer_extra_show_cols: dict                          # 同業比較表市場專屬欄位：{原始欄名: 顯示欄名}
    peer_extra_column_config: dict                      # 上述欄位對應的 st.column_config 設定
    page_top_anchor: str                                # 頁首錨點 id，"回到最上方" 連結用


def render_stock_detail(
    row: pd.Series, df: pd.DataFrame, roe_threshold: float, roe_mode: str,
    payout_threshold: float, key_prefix: str, spec: DetailCardSpec,
) -> None:
    """渲染單一股票的詳細卡片：5年 ROE 趨勢圖、五點原則逐項檢核、同業比較。

    df 為完整資料集（不受目前篩選條件影響），用於同業比較；
    key_prefix 用於區隔不同呼叫端產生的 widget key（例如快速查詢 vs 篩選結果選單），
    避免同一次 script run 中出現重複的 widget key；
    spec 是呼叫端（views/tw.py、views/us.py）建立的市場專屬設定，見 DetailCardSpec。
    """
    # 基本資料列：交易所、最新財報期別、最近年度營收、預期報酬率(IRR)。
    # 這幾欄（交易所／財報／營收／最近營收年度）不在 data_loader 的必要欄位
    # 清單內，較舊的上傳檔可能沒有，故一律用 row.get() 取值、缺值顯示「—」。
    exchange_raw = row.get("交易所")
    exchange_text = str(exchange_raw).strip() if pd.notna(exchange_raw) else "—"
    report_raw = row.get("財報")
    report_text = str(report_raw).strip() if pd.notna(report_raw) else "—"
    revenue_raw = row.get("營收")
    revenue_year_raw = row.get("最近營收年度")
    if pd.notna(revenue_raw):
        year_prefix = f"{int(revenue_year_raw)} 年 " if pd.notna(revenue_year_raw) else ""
        revenue_text = f"{year_prefix}{revenue_raw:,.0f} {spec.revenue_unit_fn(row)}"
    else:
        revenue_text = "—"
    irr_raw = row["預期報酬率"]
    irr_value_text = "—" if pd.isna(irr_raw) else f"{irr_raw:.1f}%"

    st.markdown(f"**{row['Symbol']}　{row['COMPANY']}**")
    st.caption(
        f"交易所：{exchange_text}　｜　最新財報期別：{report_text}　｜　"
        f"最近年度營收：{revenue_text}　｜　預期報酬率(IRR)：{irr_value_text}"
    )

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
        if roe_threshold > 0:  # 門檻=0 代表不限，不畫一條沒有意義的「門檻 0%」虛線
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
        # ①②的✅／❌一律採用「目前側邊欄篩選門檻與模式」判定（roe_row_passes()
        # 直接複用 filter_by_roe()），確保跟篩選結果表用的是同一套標準，
        # 不會出現「有通過篩選卻卡片顯示❌」這種矛盾。
        roe_ok = roe_row_passes(row, roe_threshold, roe_mode)
        payout_ok = None if payout_threshold <= 0 else row["預期配息率"] >= payout_threshold
        market_cap_value = row[spec.market_cap_col]
        market_cap_ok = None if pd.isna(market_cap_value) else market_cap_value >= spec.market_cap_threshold

        def mark(ok):
            if ok is None:
                return "⚠️"
            return "✅" if ok else "❌"

        roe_text = "—（無資料）" if pd.isna(row["預期ROE"]) else f"{row['預期ROE']:.2f}%"
        roe_history_text = " / ".join(
            "—" if pd.isna(row[c]) else f"{row[c]:.1f}%" for c in ROE_COLS_RECENT_TO_OLD
        )
        roe_threshold_note = (
            f"門檻 {roe_threshold:.1f}%，{ROE_FILTER_MODE_LABELS[roe_mode]}" if roe_threshold > 0 else "門檻不限"
        )
        st.markdown(
            f"- {mark(roe_ok)} ①ROE穩定：近5年ROE(近→遠) {roe_history_text}（{roe_threshold_note}，"
            f"同側邊欄篩選標準）　｜　預期ROE {roe_text}（僅供參考）"
        )
        retention_text = "—" if pd.isna(row["盈再率"]) else f"{row['盈再率']:.2f}%"
        payout_threshold_note = f"門檻 {payout_threshold:.0f}%" if payout_threshold > 0 else "門檻不限"
        st.markdown(
            f"- {mark(payout_ok)} ②配得出現金：配息率 {row['預期配息率']:.2f}%"
            f"（{payout_threshold_note}，同側邊欄篩選標準），盈再率 {retention_text}"
        )
        st.markdown(f"- ⚠️ ③不會變的公司：{spec.sector_check_text_fn(row)}，請自行判斷")
        market_cap_text = "—（無資料）" if pd.isna(market_cap_value) else spec.market_cap_value_fmt(market_cap_value)
        st.markdown(
            f"- {mark(market_cap_ok)} ④公司夠大：市值 {market_cap_text}"
            f"（門檻 {spec.market_cap_threshold_fmt(spec.market_cap_threshold)}），上市年資 ❌ 待查證"
        )
        st.markdown(f"- ❌ ⑤老闆誠信：{spec.ownership_check_label} 待查證")

        irr_text = "—（無法估算）" if pd.isna(row["預期報酬率"]) else f"{row['預期報酬率']:.1f}%"
        irr_ok = None if pd.isna(row["預期報酬率"]) else row["預期報酬率"] >= spec.irr_threshold
        st.markdown(
            f"- {mark(irr_ok)} 延伸判準：預期報酬率(IRR) {irr_text}"
            f"（課程門檻 ≥{spec.irr_threshold:.0f}%）"
        )

        verify_url = spec.verify_url_template.format(symbol=row["Symbol"])
        st.link_button(spec.verify_button_label, verify_url, key=f"{key_prefix}_verify_link")

    st.divider()
    if pd.isna(row[spec.peer_group_col]):
        st.caption(spec.peer_missing_caption)
    else:
        with st.container(border=True):
            peers = df[df[spec.peer_group_col] == row[spec.peer_group_col]].copy()
            peers = peers.sort_values(spec.market_cap_col, ascending=False, na_position="last").reset_index(drop=True)
            peers.insert(0, "排名", peers.index + 1)
            peers = spec.peer_extra_column_builder(peers)
            peers["本股"] = peers["Symbol"].apply(lambda s: "👉" if s == row["Symbol"] else "")

            my_rank_rows = peers.index[peers["Symbol"] == row["Symbol"]]
            my_rank = int(my_rank_rows[0]) + 1 if len(my_rank_rows) else None
            total_peers = len(peers)

            st.markdown(f"**同業比較 — {spec.peer_header_fn(row, total_peers)}**")
            if my_rank and pd.notna(market_cap_value):
                st.caption(
                    f"{row['COMPANY']} 市值約 {spec.market_cap_value_fmt(market_cap_value)}，"
                    f"同業市值排名第 {my_rank}/{total_peers} 名"
                )

            peer_show_cols = {
                "本股": "本股",
                "排名": "排名",
                "Symbol": "股票代號",
                "COMPANY": "公司名稱",
                spec.market_cap_col: spec.market_cap_display_label,
                "預期ROE": "預期ROE(%)",
                "預期配息率": "配息率(%)",
                **spec.peer_extra_show_cols,
            }
            peer_table = peers[list(peer_show_cols.keys())].rename(columns=peer_show_cols)
            st.dataframe(
                peer_table,
                width="stretch",
                hide_index=True,
                height=350,
                key=f"{key_prefix}_peer_table",
                column_config={
                    spec.market_cap_display_label: st.column_config.NumberColumn(format="%.1f"),
                    "預期ROE(%)": st.column_config.NumberColumn(format="%.2f"),
                    "配息率(%)": st.column_config.NumberColumn(format="%.2f"),
                    **spec.peer_extra_column_config,
                },
            )

    st.markdown(f"[⬆️ 回到最上方](#{spec.page_top_anchor})")
