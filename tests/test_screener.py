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


class TestFilterByRoeModeD:
    """模式 D（預估值版）直接用『預期ROE』欄位，邏輯最單純，適合驗證納入/排除。"""

    def test_default_threshold_excludes_low_roe_companies(self, sample):
        # 統一(1216)、華通(2313)、東哥(8478) 目前預期ROE 皆低於預設 15% 門檻
        result = filter_by_roe(sample, ["D"], DEFAULT_ROE_THRESHOLD)
        result_symbols = set(result["Symbol"])
        for sym in ["1216", "2313", "8478"]:
            row = get_row(sample, sym)
            if row["預期ROE"] < DEFAULT_ROE_THRESHOLD:
                assert sym not in result_symbols

    def test_default_threshold_includes_high_roe_companies(self, sample):
        # 旭隼(6409)、4763 目前預期ROE 應遠超 15% 門檻
        result = filter_by_roe(sample, ["D"], DEFAULT_ROE_THRESHOLD)
        result_symbols = set(result["Symbol"])
        for sym in ["6409", "4763"]:
            row = get_row(sample, sym)
            if row["預期ROE"] >= DEFAULT_ROE_THRESHOLD:
                assert sym in result_symbols

    def test_lowering_threshold_to_10_includes_borderline_companies(self, sample):
        """調降 ROE 門檻至 10% 後，統一、華通、東哥應被納入（若其預期ROE >= 10%）。"""
        result = filter_by_roe(sample, ["D"], 10.0)
        result_symbols = set(result["Symbol"])
        for sym in ["1216", "2313", "8478"]:
            row = get_row(sample, sym)
            if row["預期ROE"] >= 10.0:
                assert sym in result_symbols, f"{sym} 預期ROE={row['預期ROE']} 應在門檻10%下被納入"

    def test_threshold_slider_actually_changes_result_count(self, sample):
        strict = filter_by_roe(sample, ["D"], DEFAULT_ROE_THRESHOLD)
        loose = filter_by_roe(sample, ["D"], 10.0)
        assert len(loose) >= len(strict)


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


class TestFilterByRoeModeA:
    """模式 A（嚴格版）：5 年皆須達標，缺值視為不通過。"""

    def test_higher_threshold_never_increases_result_count(self, df):
        loose = filter_by_roe(df, ["A"], 10.0)
        strict = filter_by_roe(df, ["A"], 20.0)
        assert len(strict) <= len(loose)

    def test_missing_year_excludes_company(self, df):
        # 任一年 ROE 缺值的公司，在嚴格版下一律視為不通過（即使門檻設為0）
        has_missing = df[df[["ROE1", "ROE2", "ROE3", "ROE4", "ROE5"]].isna().any(axis=1)]
        if len(has_missing) > 0:
            sample_missing_symbol = has_missing.iloc[0]["Symbol"]
            result = filter_by_roe(df, ["A"], 0.0)
            assert sample_missing_symbol not in set(result["Symbol"])


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
