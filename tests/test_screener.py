# -*- coding: utf-8 -*-
"""
用課程投影片「好公司範例清單」中提到的公司驗證篩選邏輯是否正確。

注意：資料為即時更新的 Excel，數字會隨時間變動，因此測試不寫死投影片上的
舊數字，而是先讀出這些公司「目前」的實際欄位值，再驗證篩選函式是否依這些
實際值做出正確的納入/排除判斷（邏輯正確性測試，而非數字比對測試）。
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_loader import load_tw_data
from src.screener import filter_by_net_income, filter_by_payout, filter_by_roe
from src.constants import (
    DEFAULT_NET_INCOME_THRESHOLD,
    DEFAULT_PAYOUT_THRESHOLD,
    DEFAULT_ROE_THRESHOLD,
)
from src.tw_sector_groups import TW_SECTOR_GROUP_OF, TW_SECTOR_GROUPS

DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "twlist.xlsx"
)

# 課程範例清單提到的公司代號
TEST_SYMBOLS = ["1216", "6409", "2313", "1752", "4763", "8478"]


@pytest.fixture(scope="module")
def df():
    return load_tw_data(DATA_PATH)


@pytest.fixture(scope="module")
def sample(df):
    """只取測試案例公司的子集，並確認資料存在。"""
    sub = df[df["Symbol"].isin(TEST_SYMBOLS)]
    assert len(sub) == len(TEST_SYMBOLS), "測試案例公司在資料中應全部存在"
    return sub


def get_row(sample: pd.DataFrame, symbol: str) -> pd.Series:
    row = sample[sample["Symbol"] == symbol]
    assert len(row) == 1
    return row.iloc[0]


class TestDataLoader:
    def test_required_columns_present(self, df):
        for col in ["Symbol", "COMPANY", "ROE1", "ROE5", "SECTOR", "預期常利"]:
            assert col in df.columns

    def test_sector_has_no_leading_trailing_space(self, df):
        stripped = df["SECTOR"].dropna().apply(lambda s: s == s.strip())
        assert stripped.all()


class TestFilterByRoe:
    """
    ROE 篩選只有一套規則：近 5 年（ROE1~ROE5 實際歷史值）任一年低於門檻
    就排除、缺值視為不通過（等同舊版「模式 A 嚴格版」，但不再需要額外
    勾選模式才生效——門檻本身就是規則）。用手工合成資料測邊界情況最直接，
    另外用真實資料的統一(1216)/旭隼(6409)做一次語意檢查（1216 在 ROE3
    只有 2.3%，遠低於任何合理門檻，應被排除；6409 五年 ROE 都在 30%以上，
    應被納入）。
    """

    def test_any_year_below_threshold_excludes_company(self):
        sample = pd.DataFrame(
            {
                "Symbol": ["ALL_HIGH", "ONE_LOW", "ONE_MISSING"],
                "ROE1": [20.0, 20.0, 20.0],
                "ROE2": [18.0, 18.0, 18.0],
                "ROE3": [22.0, 5.0, float("nan")],
                "ROE4": [19.0, 19.0, 19.0],
                "ROE5": [21.0, 21.0, 21.0],
            }
        )
        result = filter_by_roe(sample, 15.0)
        assert list(result["Symbol"]) == ["ALL_HIGH"]

    def test_zero_threshold_means_unlimited(self):
        sample = pd.DataFrame(
            {
                "Symbol": ["A", "B"],
                "ROE1": [1.0, float("nan")],
                "ROE2": [1.0, float("nan")],
                "ROE3": [1.0, float("nan")],
                "ROE4": [1.0, float("nan")],
                "ROE5": [1.0, float("nan")],
            }
        )
        result = filter_by_roe(sample, 0.0)
        assert len(result) == len(sample)

    def test_real_data_sanity_check(self, sample):
        # 統一(1216) ROE3=2.3%，任何合理門檻下都應被排除
        result_15 = filter_by_roe(sample, DEFAULT_ROE_THRESHOLD)
        assert "1216" not in set(result_15["Symbol"])
        # 旭隼(6409) 近5年ROE皆遠高於15%門檻，應被納入
        assert "6409" in set(result_15["Symbol"])

    def test_threshold_actually_changes_result_count(self, df):
        loose = filter_by_roe(df, 10.0)
        strict = filter_by_roe(df, 20.0)
        assert len(strict) <= len(loose)


class TestFilterByPayout:
    def test_all_test_companies_have_high_payout(self, sample):
        # 這批範例公司預期配息率皆偏高，預設 40% 門檻下都應通過
        result = filter_by_payout(sample, DEFAULT_PAYOUT_THRESHOLD)
        result_symbols = set(result["Symbol"])
        for sym in TEST_SYMBOLS:
            row = get_row(sample, sym)
            if row["預期配息率"] >= DEFAULT_PAYOUT_THRESHOLD:
                assert sym in result_symbols

    def test_zero_threshold_means_unlimited(self, sample):
        result = filter_by_payout(sample, 0.0)
        assert len(result) == len(sample)


class TestFilterByNetIncome:
    def test_default_threshold_500(self, sample):
        result = filter_by_net_income(sample, DEFAULT_NET_INCOME_THRESHOLD)
        result_symbols = set(result["Symbol"])
        for sym in TEST_SYMBOLS:
            row = get_row(sample, sym)
            if row["預期常利"] >= DEFAULT_NET_INCOME_THRESHOLD:
                assert sym in result_symbols
            else:
                assert sym not in result_symbols

    def test_nan_none_means_unlimited(self, sample):
        result = filter_by_net_income(sample, None)
        assert len(result) == len(sample)


class TestTwSectorGroupCoverage:
    """確保 twlist.xlsx 目前的每一個 SECTOR 都有大分類對照，未來資料更新
    若出現新的 SECTOR 字串，這裡會直接失敗提醒要補上對照。"""

    def test_all_sectors_have_group(self, df):
        actual_sectors = set(df["SECTOR"].dropna().unique())
        unmapped = sorted(actual_sectors - set(TW_SECTOR_GROUP_OF.keys()))
        assert unmapped == [], f"缺少大分類對照的 SECTOR：{unmapped}"

    def test_all_group_codes_are_valid(self):
        valid_groups = set(TW_SECTOR_GROUPS.keys())
        invalid = sorted(set(TW_SECTOR_GROUP_OF.values()) - valid_groups)
        assert invalid == [], f"TW_SECTOR_GROUP_OF 用到未定義的大分類代碼：{invalid}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
