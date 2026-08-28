# -*- coding: utf-8 -*-
"""
Streamlit UI 共用元件（不含任何特定市場的資料邏輯，台股／美股頁面共用）
"""
from __future__ import annotations

import io
from typing import Callable, Optional, Sequence

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


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


def scroll_to_anchor(anchor_id: str) -> None:
    """把主畫面（父層 iframe）平滑捲動到指定錨點 id。

    用於「點篩選結果表格某一列 -> 跳到下方個股詳細檢視區塊」的體驗：
    st.dataframe 點選只會更新內部狀態，畫面不會自動捲動，這裡注入一小段
    JS 主動捲過去。錨點本身需由呼叫端事先放好（例如
    st.markdown(f'<div id="{anchor_id}"></div>', unsafe_allow_html=True)）。
    """
    components.html(
        f"""
        <script>
            setTimeout(function () {{
                const doc = window.parent.document;
                const el = doc.getElementById('{anchor_id}');
                if (el) {{ el.scrollIntoView({{behavior: 'smooth', block: 'start'}}); }}
            }}, 150);
        </script>
        """,
        height=0,
    )


# max_entries 限制以下兩個快取的筆數上限：CSV／Excel bytes 都是用「表格內容」
# 當快取鍵，使用者每調整一次篩選條件、只要湊出一個沒算過的結果集，就會多一筆
# 快取（美股全量一筆 Excel bytes 約 2.76 MB）。不設上限的話，Streamlit 預設
# 會把每一種篩選組合都留著不釋放，滑幾次滑桿就能吃掉數十 MB，對 Streamlit
# Community Cloud 的記憶體上限是明顯風險，設小上限讓舊的自動被淘汰。
# 台股／美股頁面共用同一份快取（函式本身不含市場邏輯），互不干擾：快取鍵是
# 傳入表格的內容雜湊，兩個市場的表格內容不同，天然不會撞鍵。
@st.cache_data(show_spinner=False, max_entries=4)
def to_csv_bytes(table: pd.DataFrame) -> bytes:
    return table.to_csv(index=False).encode("utf-8-sig")


@st.cache_data(show_spinner=False, max_entries=4)
def to_excel_bytes(table: pd.DataFrame) -> bytes:
    """把篩選結果表轉成 Excel bytes，供下載按鈕使用。

    這裡加上 @st.cache_data 是因為 st.download_button 每次 script rerun
    都要重新取得 data= 參數（哪怕使用者根本沒按下載），而 ExcelWriter
    對上萬列資料的寫入成本不小（實測美股 12,497 列約 2 秒）。
    傳入的 table 需為欄位皆為純量值的版本（可直接寫入 Excel）。
    """
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        table.to_excel(writer, index=False, sheet_name="篩選結果")
    return excel_buffer.getvalue()


def render_download_buttons(table: pd.DataFrame, key_prefix: str, file_stem: str) -> None:
    """篩選結果表格的下載按鈕：CSV 直接下載（轉換快，全量約 0.2 秒）；
    Excel 因為寫入成本高很多（全量約 6 秒），而 download_button 的 data=
    參數不論使用者有沒有按下載、每次 rerun 都要重新求值，若直接放
    to_excel_bytes(table)，等於每次調整篩選條件、只要換到一個沒算過的
    結果集就要白白付這筆成本——即使使用者從未點過下載。因此改成「先按
    『產生 Excel』才真的計算」，算完的結果存在 session_state，並用內容
    雜湊（table_fingerprint）判斷篩選結果是否已經變了、需要作廢重算，
    避免使用者按了產生之後又調整篩選條件，卻抓到上一次篩選結果的舊檔案。

    key_prefix 需頁面唯一（例如 "tw"、"us"），用來區隔 session_state 與
    widget key；file_stem 是下載檔名（不含副檔名）。
    """
    dl_cols = st.columns(2)
    dl_cols[0].download_button(
        "⬇️ 下載 CSV", data=to_csv_bytes(table), file_name=f"{file_stem}.csv", mime="text/csv",
        key=f"{key_prefix}_dl_csv",
    )
    with dl_cols[1]:
        bytes_key = f"{key_prefix}_excel_bytes"
        fp_key = f"{key_prefix}_excel_fingerprint"
        if bytes_key not in st.session_state:
            st.session_state[bytes_key] = None
        if fp_key not in st.session_state:
            st.session_state[fp_key] = None

        table_fingerprint = int(pd.util.hash_pandas_object(table, index=False).sum())
        if st.session_state[fp_key] != table_fingerprint:
            st.session_state[bytes_key] = None
            st.session_state[fp_key] = table_fingerprint

        if st.session_state[bytes_key] is None:
            if st.button("🗂️ 產生 Excel 下載檔", key=f"{key_prefix}_gen_xlsx"):
                st.session_state[bytes_key] = to_excel_bytes(table)
                st.rerun()
        else:
            st.download_button(
                "⬇️ 下載 Excel",
                data=st.session_state[bytes_key],
                file_name=f"{file_stem}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"{key_prefix}_dl_xlsx",
            )


def init_two_level_sector_state(
    group_key: str, sectors_key: str, prev_groups_key: str, all_groups: Sequence[str],
) -> None:
    """兩層式產業篩選（大分類→細分產業）的 session_state 初始化。

    必須在任何側邊欄 widget 建立之前呼叫（通常在 init_session_defaults()
    之後、大分類 multiselect widget 之前）。
    """
    if st.session_state.get(group_key) is None:
        st.session_state[group_key] = list(all_groups)
    if st.session_state.get(prev_groups_key) is None:
        st.session_state[prev_groups_key] = list(st.session_state[group_key])


def sync_two_level_sector_state(
    selected_groups: Sequence[str], sectors_key: str, prev_groups_key: str,
    sectors_in_groups: Sequence[str], group_of: Callable[[str], str],
    sort_key: Optional[Callable[[str], object]] = None,
) -> None:
    """大分類 multiselect 渲染完成後呼叫，同步細分產業的選取狀態。

    - 大分類縮小範圍時，先前選的細分產業若已不在範圍內就移除，避免
      multiselect 的 value 超出 options 而噴錯。
    - 大分類「新增」範圍時，新出現的細分產業預設一併勾選——否則會卡在
      縮小時的殘留選取，使用者把大分類選回全部後，細分產業與篩選結果
      卻還停在縮小時的狀態，像是「選回全部」沒有生效（修正前的 bug：
      先縮小到只剩一個大分類、再選回全部，篩選結果家數不會變回全部）。

    sectors_in_groups 由呼叫端算好傳入（不同市場的排序／翻譯邏輯不同）；
    group_of 是「SECTOR 字串 -> 大分類代碼」的函式；sort_key 是細分產業
    重新排序時用的排序鍵（例如美股頁面依中文翻譯排序），預設為字母序。
    """
    previously_selected_groups = set(st.session_state[prev_groups_key])
    newly_added_groups = set(selected_groups) - previously_selected_groups
    newly_available_sectors = {s for s in sectors_in_groups if group_of(s) in newly_added_groups}

    if st.session_state.get(sectors_key) is None:
        st.session_state[sectors_key] = list(sectors_in_groups)
    else:
        kept = [s for s in st.session_state[sectors_key] if s in sectors_in_groups]
        st.session_state[sectors_key] = sorted(set(kept) | newly_available_sectors, key=sort_key)

    st.session_state[prev_groups_key] = list(selected_groups)
