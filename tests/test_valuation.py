# -*- coding: utf-8 -*-
"""
驗證估價區間判斷（filter_by_valuation() / valuation_labels()）正確排除
「貴價／淑價 <= 0」的無效資料，不會被誤判為『昂貴價』。

背景：實測美股清單中有 130 筆極低價股票『貴價』『淑價』其中一項或兩項
恰為 0（研判是資料源對極小數值四捨五入到顯示精度的副作用），若只排除
NaN 缺值、不排除 <= 0，這些股票的收盤價（同樣是正數）會 >= 0 的『貴價』
而被誤判為『昂貴價』。
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.screener import filter_by_valuation, valuation_labels


def _build_df():
    df = pd.DataFrame(
        {
            "Symbol": ["NORMAL_CHEAP", "NORMAL_FAIR", "NORMAL_EXPENSIVE", "BOTH_ZERO", "LOW_ZERO", "HIGH_ZERO", "NO_DATA"],
            "收盤價": [10.0, 10.0, 10.0, 0.02, 0.05, 5.0, 10.0],
            "淑價": [12.0, 8.0, 8.0, 0.0, 0.0, 4.0, float("nan")],
            "貴價": [15.0, 12.0, 9.0, 0.0, 0.1, 0.0, 20.0],
        }
    )
    return df.set_index("Symbol", drop=False)


def test_zero_or_negative_boundary_excluded_from_expensive():
    df = _build_df()
    labels = valuation_labels(df)

    assert labels["NORMAL_CHEAP"] == "便宜價"
    assert labels["NORMAL_FAIR"] == "合理價"
    assert labels["NORMAL_EXPENSIVE"] == "昂貴價"
    # 這四種缺陷資料在修復前都會被誤判為「昂貴價」，修復後應一律「無法估價」
    assert labels["BOTH_ZERO"] == "無法估價"
    assert labels["LOW_ZERO"] == "無法估價"
    assert labels["HIGH_ZERO"] == "無法估價"
    assert labels["NO_DATA"] == "無法估價"


def test_filter_by_valuation_excludes_zero_boundary_rows():
    df = _build_df()

    expensive = filter_by_valuation(df, "expensive")
    assert list(expensive["Symbol"]) == ["NORMAL_EXPENSIVE"]

    cheap = filter_by_valuation(df, "cheap")
    assert list(cheap["Symbol"]) == ["NORMAL_CHEAP"]

    fair = filter_by_valuation(df, "fair")
    assert list(fair["Symbol"]) == ["NORMAL_FAIR"]
