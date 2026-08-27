# -*- coding: utf-8 -*-
"""
Streamlit UI 共用元件（不含任何特定市場的資料邏輯，台股／美股頁面共用）
"""
from __future__ import annotations

import streamlit as st


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
