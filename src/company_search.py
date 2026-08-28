# -*- coding: utf-8 -*-
"""
「快速查詢股票」分頁的股票代號／公司名稱搜尋邏輯（純函式，供 views/tw.py 呼叫）。

拆成獨立、不依賴 Streamlit 的純函式，是為了能直接寫單元測試（Streamlit 頁面
腳本本身不方便單獨測試這段邏輯），也讓這裡目前只有台股在用的「別名／
異體字」加強邏輯之後如果美股也需要類似處理時，有現成的地方可以擴充，而不是
直接複製貼上一份到 views/us.py。
"""
from __future__ import annotations

import pandas as pd

from .tw_company_aliases import TW_COMPANY_ALIASES


def _normalize_tw_text(s: str) -> str:
    """統一「臺」「台」異體字。

    twlist.xlsx 目前有 12 家公司的登記全名用「臺」而非現在較常打的「台」
    （例如「臺灣水泥股份有限公司」），使用者打「台泥」「台灣水泥」都因為
    這個異體字差異直接落到「找不到符合的股票」。這是系統性、影響任何查詢
    字串的問題（不限於特定公司），所以在比對前統一正規化，而不是逐家公司
    另外收錄別名。
    """
    return s.replace("臺", "台")


def search_tw_companies(df: pd.DataFrame, query: str) -> pd.DataFrame:
    """台股快速查詢：股票代號／公司登記全名子字串比對（不分大小寫），
    疊加「臺／台」異體字正規化與常見簡稱對照表（TW_COMPANY_ALIASES），
    讓「台積電」「TSMC」「台泥」這類多數人實際會打的查法也能找到對應公司，
    而不是只能用登記全名（例如「台灣積體電路製造股份有限公司」）才查得到。

    query 為空字串（或全空白）時回傳空結果，呼叫端應先檢查再顯示提示文字，
    不依賴這裡回傳空結果來判斷「使用者還沒輸入」。
    """
    q = query.strip()
    if not q:
        return df.iloc[0:0]

    q_norm = _normalize_tw_text(q)
    company_norm = df["COMPANY"].str.replace("臺", "台", regex=False)

    mask = (
        df["Symbol"].str.contains(q, case=False, na=False, regex=False)
        | company_norm.str.contains(q_norm, case=False, na=False, regex=False)
    )

    q_norm_lower = q_norm.lower()
    alias_symbols = {
        sym
        for alias, sym in TW_COMPANY_ALIASES.items()
        if (alias_norm := _normalize_tw_text(alias).lower()) in q_norm_lower
        or q_norm_lower in alias_norm
    }
    if alias_symbols:
        mask = mask | df["Symbol"].isin(alias_symbols)

    return df[mask]
