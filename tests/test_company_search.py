# -*- coding: utf-8 -*-
"""
台股快速查詢（src/company_search.py、src/tw_company_aliases.py）測試。

用真實 twlist.xlsx 驗證：① 別名對照表裡的每一筆都要能在目前資料中解析到
存在的股票（防止資料更新後某檔下市／代號變更，對照表卻沒跟著更新，
變成指向不存在公司的死連結）；② 常見的查詢方式（簡稱、英文名、
「臺／台」異體字）都要能查到對應公司。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.company_search import search_tw_companies
from src.data_loader import load_tw_data
from src.tw_company_aliases import TW_COMPANY_ALIASES

DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "twlist.xlsx"
)


@pytest.fixture(scope="module")
def df():
    return load_tw_data(DATA_PATH)


class TestAliasTableIntegrity:
    """確保別名表不會指向目前資料中已經不存在的股票代號（例如下市、
    代號變更），這種情況應該讓測試失敗、提醒維護者更新對照表，而不是
    讓使用者查到 KeyError 或悄悄查不到。"""

    def test_every_alias_symbol_exists_in_current_data(self, df):
        known_symbols = set(df["Symbol"])
        missing = {
            alias: sym for alias, sym in TW_COMPANY_ALIASES.items() if sym not in known_symbols
        }
        assert missing == {}, f"以下別名對照到目前資料中不存在的股票代號：{missing}"


class TestSearchTwCompanies:
    def test_empty_query_returns_empty(self, df):
        assert len(search_tw_companies(df, "")) == 0
        assert len(search_tw_companies(df, "   ")) == 0

    def test_symbol_exact_match(self, df):
        result = search_tw_companies(df, "2330")
        assert "2330" in set(result["Symbol"])

    def test_registered_full_name_substring(self, df):
        result = search_tw_companies(df, "台灣積體電路製造")
        assert "2330" in set(result["Symbol"])

    def test_alias_nickname_finds_company(self, df):
        # 「台積電」不是登記全名「台灣積體電路製造股份有限公司」的子字串，
        # 修正前用原本的純子字串比對查不到，是這次優化要解決的原始案例。
        result = search_tw_companies(df, "台積電")
        assert "2330" in set(result["Symbol"])

    def test_alias_english_name_finds_company(self, df):
        result = search_tw_companies(df, "TSMC")
        assert "2330" in set(result["Symbol"])
        result_lower = search_tw_companies(df, "tsmc")
        assert "2330" in set(result_lower["Symbol"])

    def test_traditional_variant_character_normalized(self, df):
        # 臺灣水泥股份有限公司登記名稱用「臺」，使用者常打的「台泥」
        # 「台灣水泥」都應該能找到，不受這個異體字差異影響。
        for query in ("台泥", "台灣水泥"):
            result = search_tw_companies(df, query)
            assert "1101" in set(result["Symbol"]), f"query={query!r}"

    def test_no_match_returns_empty(self, df):
        result = search_tw_companies(df, "zzz這個字串不會對應到任何公司zzz")
        assert len(result) == 0

    def test_regex_special_characters_do_not_crash(self, df):
        # 子字串比對走 regex=False，特殊字元應被當純文字處理，不應拋例外。
        for query in ("(", "[", "2330(", ".*"):
            result = search_tw_companies(df, query)
            assert result is not None
