# -*- coding: utf-8 -*-
"""
驗證 compute_roe_stability_bulk()（向量化版本）與 compute_roe_stability()
（逐列版本，原本的正確性基準）在各種邊界情況下回傳完全一致的結果。

向量化版本是為了解決效能問題而寫的（美股 12,497 列，逐列版本約 1.2 秒／次，
是側邊欄「符合 N 家」即時計數的瓶頸來源），但兩個數學上不同的實作方式
（np.polyfit 逐列 vs. OLS 公式整批運算；「壓縮後相鄰差」vs.「所有位置對」
判斷單調性）必須先證明語意等價，才能安心互換使用，因此這裡沒有依賴
data/twlist.xlsx 的實際資料（真實資料不見得覆蓋得到所有邊界情況），
而是手工建構涵蓋以下情況的合成資料：
    - 全缺值 / 只有 1 個有效值（資料不足）
    - 5 年皆有值、一致向上／一致向下
    - 中間有缺值但仍維持單調（驗證「所有位置對」判斷法與「壓縮後相鄰差」
      判斷法在有缺值時仍等價）
    - 持平（標準差小、斜率小）
    - 忽高忽低（不滿足任何單調或持平條件）
    - 恰好 2 個有效值（迴歸的最小樣本數邊界）
    - 5 年數值皆相同（std=0、slope=0，同時滿足 monotonic_up 與
      monotonic_down，驗證 elif 優先序有沒有被向量化版本破壞）
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.constants import ROE_COLS_RECENT_TO_OLD
from src.scoring import compute_roe_stability, compute_roe_stability_bulk

# 每個 case 用「近→遠」（ROE1..ROE5）的順序寫，和 twlist.xlsx 欄位順序一致
CASES = {
    "全缺值": [np.nan, np.nan, np.nan, np.nan, np.nan],
    "僅1個有效值": [np.nan, np.nan, np.nan, np.nan, 10.0],
    "恰好2個有效值_上升": [np.nan, np.nan, np.nan, 5.0, 15.0],
    "恰好2個有效值_持平": [np.nan, np.nan, np.nan, 10.1, 10.0],
    "5年一致向上": [20.0, 16.0, 12.0, 8.0, 4.0],
    "5年一致向下": [4.0, 8.0, 12.0, 16.0, 20.0],
    "有缺值仍單調向上": [np.nan, 18.0, np.nan, 10.0, np.nan],
    "有缺值仍單調向下": [np.nan, 10.0, np.nan, 18.0, np.nan],
    "持平": [15.2, 14.8, 15.5, 14.9, 15.1],
    "忽高忽低": [30.0, 5.0, 25.0, 8.0, 20.0],
    "5年數值全相同": [10.0, 10.0, 10.0, 10.0, 10.0],
    "有缺值且忽高忽低": [30.0, np.nan, 5.0, np.nan, 25.0],
}


def _build_df() -> pd.DataFrame:
    rows = {name: dict(zip(ROE_COLS_RECENT_TO_OLD, values)) for name, values in CASES.items()}
    return pd.DataFrame.from_dict(rows, orient="index")


def test_bulk_matches_row_wise_on_synthetic_cases():
    df = _build_df()
    bulk = compute_roe_stability_bulk(df)

    for name in df.index:
        row_result = compute_roe_stability(df.loc[name])
        bulk_result = bulk.loc[name]

        assert bulk_result["trend"] == row_result["trend"], (
            f"[{name}] trend 不一致：bulk={bulk_result['trend']!r}, "
            f"row-wise={row_result['trend']!r}"
        )
        assert bulk_result["trend_label"] == row_result["trend_label"], name
        assert int(bulk_result["n_years"]) == row_result["n_years"], name

        if pd.isna(row_result["std"]):
            assert pd.isna(bulk_result["std"]), name
        else:
            assert bulk_result["std"] == pytest_approx(row_result["std"]), name

        if pd.isna(row_result["slope"]):
            assert pd.isna(bulk_result["slope"]), name
        else:
            assert bulk_result["slope"] == pytest_approx(row_result["slope"]), name


def pytest_approx(value, tol=1e-9):
    """輕量版 pytest.approx，避免額外依賴（本檔已可直接用 pytest，但保持獨立函式方便閱讀）。"""
    import pytest

    return pytest.approx(value, abs=tol)


def test_bulk_matches_row_wise_on_real_tw_data():
    """再拿真實資料交叉驗證一次（涵蓋合成 case 之外可能沒想到的欄位組合）。

    compute_roe_stability() 現在內部直接呼叫 compute_roe_stability_bulk()
    （見 src/scoring.py 的說明），所以這個測試理論上不可能再抓到兩者不一致
    ——除非未來有人又把兩者拆成各自獨立的實作。保留這個測試就是為了在
    那種情況發生時立刻炸掉，而不是留給浮點數邊界值默默產生分類不一致
    （這正是這兩個測試最早發現的真實 bug：全台股 2,072 筆資料一致，
    但美股 12,497 筆資料曾有 9 筆在 FLAT_SLOPE_THRESHOLD 邊界附近分類
    不一致，詳見下方 test_bulk_matches_row_wise_on_real_us_data_sample()）。
    """
    from src.data_loader import load_tw_data

    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "twlist.xlsx"
    )
    df = load_tw_data(data_path)

    bulk = compute_roe_stability_bulk(df)
    row_wise_trend = df.apply(lambda r: compute_roe_stability(r)["trend"], axis=1)

    mismatches = (bulk["trend"] != row_wise_trend.values).sum()
    assert mismatches == 0, f"{mismatches} 列的 trend 分類不一致"


def test_bulk_matches_row_wise_on_real_us_data_sample():
    """美股資料量較大（12,497 列），逐列版本 compute_roe_stability() 現在
    每次呼叫都要建立一個 1 列 DataFrame，全量跑一次約 18 秒，對測試套件
    來說太慢；改成固定亂數種子抽樣，兼顧覆蓋率與測試速度。

    抽樣涵蓋全部列而非只挑「看起來像邊界」的列，是刻意的：這個測試最早
    就是靠對全量資料做交叉驗證才抓到 FLAT_SLOPE_THRESHOLD 邊界的浮點數
    不一致（見 test_bulk_matches_row_wise_on_real_tw_data 的說明），
    人工去猜「哪些列可能踩到邊界」並不可靠。
    """
    from src.data_loader import load_us_data

    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "uslist.xlsx"
    )
    df = load_us_data(data_path)
    sample = df.sample(n=min(500, len(df)), random_state=42)

    bulk = compute_roe_stability_bulk(sample)
    row_wise_trend = sample.apply(lambda r: compute_roe_stability(r)["trend"], axis=1)

    mismatches = (bulk["trend"] != row_wise_trend.values).sum()
    assert mismatches == 0, f"{mismatches} 列的 trend 分類不一致"
