# -*- coding: utf-8 -*-
"""
美股（uslist.xlsx）資料讀取與篩選邏輯測試。

screener.py / scoring.py 的欄位命名與台股清單相同，因此篩選函式本身不需要
另外實作，這裡只驗證：① load_us_data 能正確讀入美股特有欄位、
② 篩選函式套用在美股資料上邏輯依然正確（用幾家知名公司驗證納入/排除）。
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_loader import load_us_data
from src.screener import filter_by_net_income, filter_by_payout, filter_by_roe
from src.constants import DEFAULT_PAYOUT_THRESHOLD_US, DEFAULT_ROE_THRESHOLD_US
from src.us_sector_i18n import US_SECTOR_GROUPS, US_SECTOR_INFO

DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "uslist.xlsx"
)

TEST_SYMBOLS = ["AAPL", "MSFT", "KO"]


@pytest.fixture(scope="module")
def df():
    return load_us_data(DATA_PATH)


@pytest.fixture(scope="module")
def sample(df):
    sub = df[df["Symbol"].isin(TEST_SYMBOLS)]
    assert len(sub) == len(TEST_SYMBOLS), "測試案例公司在資料中應全部存在"
    return sub


def get_row(sample: pd.DataFrame, symbol: str) -> pd.Series:
    row = sample[sample["Symbol"] == symbol]
    assert len(row) == 1
    return row.iloc[0]


class TestUsDataLoader:
    def test_required_columns_present(self, df):
        for col in ["Symbol", "COMPANY", "ROE1", "ROE5", "SECTOR", "Industry", "COUNTRY", "財報幣別", "市值($m)"]:
            assert col in df.columns

    def test_sector_has_no_leading_trailing_space(self, df):
        stripped = df["SECTOR"].dropna().apply(lambda s: s == s.strip())
        assert stripped.all()

    def test_empty_sector_normalized_to_na(self, df):
        assert not (df["SECTOR"].dropna() == "").any()

    def test_multiple_currencies_present(self, df):
        # SPEC.md 明確提到美股清單涵蓋多種財報幣別，非全為 USD
        assert df["財報幣別"].nunique() > 1


class TestUsFilterByRoe:
    def test_default_threshold_excludes_low_roe_companies(self, sample):
        result = filter_by_roe(sample, ["D"], DEFAULT_ROE_THRESHOLD_US)
        result_symbols = set(result["Symbol"])
        for sym in TEST_SYMBOLS:
            row = get_row(sample, sym)
            if row["預期ROE"] < DEFAULT_ROE_THRESHOLD_US:
                assert sym not in result_symbols

    def test_default_threshold_includes_high_roe_companies(self, sample):
        result = filter_by_roe(sample, ["D"], DEFAULT_ROE_THRESHOLD_US)
        result_symbols = set(result["Symbol"])
        for sym in TEST_SYMBOLS:
            row = get_row(sample, sym)
            if row["預期ROE"] >= DEFAULT_ROE_THRESHOLD_US:
                assert sym in result_symbols


class TestUsFilterByPayout:
    def test_zero_threshold_means_unlimited(self, sample):
        result = filter_by_payout(sample, 0.0)
        assert len(result) == len(sample)

    def test_threshold_filters_correctly(self, sample):
        result = filter_by_payout(sample, DEFAULT_PAYOUT_THRESHOLD_US)
        result_symbols = set(result["Symbol"])
        for sym in TEST_SYMBOLS:
            row = get_row(sample, sym)
            if row["預期配息率"] >= DEFAULT_PAYOUT_THRESHOLD_US:
                assert sym in result_symbols
            else:
                assert sym not in result_symbols


class TestUsFilterByNetIncome:
    def test_nan_none_means_unlimited(self, sample):
        result = filter_by_net_income(sample, None)
        assert len(result) == len(sample)

    def test_high_threshold_excludes_small_companies(self, df):
        # 用一個遠高於絕大多數公司淨利的門檻，確保篩選確實有縮小範圍
        loose = filter_by_net_income(df, 0.0)
        strict = filter_by_net_income(df, 50000.0)
        assert len(strict) < len(loose)


class TestUsSectorI18nCoverage:
    """確保 uslist.xlsx 目前的每一個 SECTOR 都有中文翻譯與大分類對照，
    未來資料更新若出現新的 SECTOR 字串，這裡會直接失敗提醒要補上對照，
    而不是讓使用者在 UI 上默默看到英文原文或被歸到「其他」。"""

    def test_all_sectors_have_translation(self, df):
        actual_sectors = set(df["SECTOR"].dropna().unique())
        unmapped = sorted(actual_sectors - set(US_SECTOR_INFO.keys()))
        assert unmapped == [], f"缺少中文對照的 SECTOR：{unmapped}"

    def test_all_group_codes_are_valid(self):
        valid_groups = set(US_SECTOR_GROUPS.keys())
        invalid = sorted({group for _, group in US_SECTOR_INFO.values()} - valid_groups)
        assert invalid == [], f"US_SECTOR_INFO 用到未定義的大分類代碼：{invalid}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
