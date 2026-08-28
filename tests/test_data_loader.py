# -*- coding: utf-8 -*-
"""
data_loader.py 的邊界情況測試。

原本這個模組只在其他測試檔案裡被當成 fixture 間接用到（只走過 happy path），
缺欄位／壞檔以外的錯誤分支、get_data_date() 對非預期型別的處理完全沒測到，
這裡補上，對應修正過的兩個 bug：
- get_data_date() 對 datetime／字串型別的「收盤日」會直接 crash（原本只假設
  一定是 8 碼數字）。
- load_tw_data() 沒有反向擋掉「看起來是美股清單」的檔案，會用台股口徑
  （市值單位億元台幣、MOPS 查證連結…）悄悄算出一堆錯誤數字。
"""
import io
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_loader import DataLoadError, get_data_date, load_tw_data, load_us_data

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
TW_DATA_PATH = os.path.join(DATA_DIR, "twlist.xlsx")
US_DATA_PATH = os.path.join(DATA_DIR, "uslist.xlsx")


@pytest.fixture(scope="module")
def tw_df():
    return load_tw_data(TW_DATA_PATH)


def _to_excel_buffer(df: pd.DataFrame) -> io.BytesIO:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    buf.seek(0)
    return buf


class TestLoadTwDataRejectsUsShapedFile:
    def test_uslist_is_rejected_by_tw_loader(self):
        """uslist.xlsx 具備 twlist.xlsx REQUIRED_COLUMNS 的全部欄位（同一套
        工具產生，只是「多」欄位），單靠缺欄位檢查擋不住，必須額外用美股
        獨有欄位（Industry／COUNTRY／市值($m)）反向擋下。"""
        with pytest.raises(DataLoadError, match="美股清單"):
            load_tw_data(US_DATA_PATH)

    def test_own_data_still_loads_fine(self, tw_df):
        assert len(tw_df) > 0

    def test_us_loader_still_accepts_uslist(self):
        df = load_us_data(US_DATA_PATH)
        assert len(df) > 0


class TestGetDataDate:
    def test_numeric_yyyymmdd(self, tw_df):
        sample = tw_df.head(5).copy()
        sample["收盤日"] = 20260826.0
        result = get_data_date(load_tw_data(_to_excel_buffer(sample)))
        assert result == "2026-08-26"

    def test_datetime_column(self, tw_df):
        """Excel 儲存格若設成日期格式，pd.read_excel 會直接讀成 Timestamp，
        原本的 int(max_date) 對此會直接拋 TypeError。"""
        sample = tw_df.head(5).copy()
        sample["收盤日"] = pd.to_datetime("2026-08-26")
        result = get_data_date(load_tw_data(_to_excel_buffer(sample)))
        assert result == "2026-08-26"

    def test_string_date_column(self, tw_df):
        sample = tw_df.head(5).copy()
        sample["收盤日"] = "2026-08-26"
        result = get_data_date(load_tw_data(_to_excel_buffer(sample)))
        assert result == "2026-08-26"

    def test_empty_dataframe_returns_unknown(self, tw_df):
        sample = tw_df.head(0).copy()
        assert get_data_date(load_tw_data(_to_excel_buffer(sample))) == "未知"

    def test_all_missing_returns_unknown(self, tw_df):
        sample = tw_df.head(5).copy()
        sample["收盤日"] = None
        assert get_data_date(load_tw_data(_to_excel_buffer(sample))) == "未知"

    def test_missing_column_returns_unknown(self):
        df = pd.DataFrame({"Symbol": ["1101"]})
        assert get_data_date(df) == "未知"

    def test_mixed_incomparable_types_does_not_crash(self):
        """收盤日欄位若混雜 datetime／字串／數字（例如手動編輯過的上傳檔），
        Series.max() 跨型別比較會拋 TypeError；這裡只要求不 crash、
        回傳「未知」，不要求解析出正確日期。"""
        df = pd.DataFrame({
            "收盤日": [pd.to_datetime("2026-08-26"), "not-a-date", 123],
        })
        assert get_data_date(df) == "未知"
