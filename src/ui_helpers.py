# -*- coding: utf-8 -*-
"""
Streamlit UI 共用元件（不含任何特定市場的資料邏輯，台股／美股頁面共用）
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .constants import ROE_YEAR_LABELS_OLD_TO_NEW


def synced_slider(label: str, key_prefix: str, min_value: float, max_value: float,
                   step: float, help: str = None, disabled: bool = False, container=None) -> float:
    """
    滑桿 + 數字輸入框並排，兩者互相同步，方便滑桿拉不準時直接輸入精確數值。
    回傳目前生效的門檻值。

    key_prefix 需在同一個 Streamlit session 內全域唯一（跨頁面也算），
    因此呼叫端請務必加上頁面專屬前綴（例如 "tw_"、"us_"），
    避免台股／美股頁面的 session_state 互相覆蓋。

    container 預設為 st.sidebar（維持原本「側邊欄頂層」的用法）。若要把這個元件
    放進側邊欄裡的 st.sidebar.expander(...) 等巢狀容器，請在該 `with` 區塊內
    呼叫並傳入 container=st（裸的 st 模組），讓內部的 columns 依當前的容器脈絡
    渲染，而不是被強制拉回側邊欄最外層。
    """
    slider_key = f"{key_prefix}_slider"
    input_key = f"{key_prefix}_input"

    def _sync_from_slider():
        st.session_state[input_key] = st.session_state[slider_key]

    def _sync_from_input():
        st.session_state[slider_key] = st.session_state[input_key]

    if container is None:
        container = st.sidebar
    col_slider, col_input = container.columns([3, 1])
    with col_slider:
        st.slider(
            label, min_value=min_value, max_value=max_value, step=step,
            key=slider_key, help=help, disabled=disabled, on_change=_sync_from_slider,
        )
    with col_input:
        st.number_input(
            label, min_value=min_value, max_value=max_value, step=step,
            key=input_key, disabled=disabled, on_change=_sync_from_input,
            label_visibility="collapsed",
        )
    return st.session_state[slider_key]


def expand_roe_trend_column(table: pd.DataFrame, trend_col: str = "5年ROE趨勢") -> pd.DataFrame:
    """
    把畫面顯示用的『5年ROE趨勢』欄位（每個儲存格是一個 Python list，只有
    st.dataframe 的 LineChartColumn 看得懂）展開成 5 個獨立數值欄位。

    CSV／Excel 下載原本各自處理這個問題：CSV 直接輸出整欄，結果是每格
    一串 "[9.0, 2.3, 3.2, 3.5, 1.9]" 這樣的字串，沒辦法在 Excel 裡直接
    拿來畫圖或算數；Excel 版本則乾脆把整欄刪掉，兩種下載格式的欄位因此
    對不起來。這裡統一改成展開成 5 欄實際數字（欄名為「ROE(5年前)」……
    「ROE(最近一年)」），CSV／Excel 都呼叫這個函式，欄位才會一致，
    數字也才是真的能在試算表裡使用的數值而非字串。
    """
    out = table.drop(columns=[trend_col]).copy()
    year_cols = [f"ROE({label})" for label in ROE_YEAR_LABELS_OLD_TO_NEW]
    trend_matrix = pd.DataFrame(table[trend_col].tolist(), columns=year_cols, index=table.index)
    return pd.concat([out, trend_matrix], axis=1)
