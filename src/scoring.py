# -*- coding: utf-8 -*-
"""
ROE 穩定度評分、五點覆蓋度計算
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .constants import (
    COVERAGE_AUTO_ITEMS,
    COVERAGE_TOTAL,
    ROE_COLS_RECENT_TO_OLD,
    ROE_TREND_LABELS,
)

# 趨勢分類的容忍門檻（判斷「持平」用的標準差上限、判斷「一致向上/向下」用的斜率下限）
FLAT_STD_THRESHOLD = 3.0   # 標準差 < 3 個百分點視為波動很小
FLAT_SLOPE_THRESHOLD = 1.0  # 斜率絕對值 < 1 個百分點/年視為持平
TREND_SLOPE_THRESHOLD = 0.5  # 單調上升/下降時，斜率需超過此值才算有意義的趨勢


def compute_roe_stability(row: pd.Series) -> dict:
    """
    計算一列資料的 5 年 ROE 穩定度指標。

    回傳 dict：
        std: 標準差（可用年度）
        slope: 線性回歸斜率（每年變化的百分點，時間由舊到新）
        trend: 趨勢分類代碼（up/flat/down/volatile/insufficient）
        trend_label: 趨勢分類中文標籤
        n_years: 可用（非缺值）年度數
    """
    # ROE_COLS_RECENT_TO_OLD = [ROE1..ROE5]，由近到遠；轉成「由舊到新」供回歸使用
    values_recent_to_old = [row.get(col) for col in ROE_COLS_RECENT_TO_OLD]
    values_old_to_new = list(reversed(values_recent_to_old))

    arr = np.array(values_old_to_new, dtype=float)
    valid_mask = ~np.isnan(arr)
    valid_values = arr[valid_mask]
    n_years = int(valid_mask.sum())

    if n_years < 2:
        return {
            "std": np.nan,
            "slope": np.nan,
            "trend": "insufficient",
            "trend_label": ROE_TREND_LABELS["insufficient"],
            "n_years": n_years,
        }

    x = np.arange(len(arr))[valid_mask]
    std = float(np.std(valid_values))
    slope = float(np.polyfit(x, valid_values, 1)[0])
    diffs = np.diff(valid_values)

    monotonic_up = bool(np.all(diffs >= -1e-9))
    monotonic_down = bool(np.all(diffs <= 1e-9))

    if monotonic_up and slope > TREND_SLOPE_THRESHOLD:
        trend = "up"
    elif monotonic_down and slope < -TREND_SLOPE_THRESHOLD:
        trend = "down"
    elif std < FLAT_STD_THRESHOLD and abs(slope) < FLAT_SLOPE_THRESHOLD:
        trend = "flat"
    else:
        trend = "volatile"

    return {
        "std": std,
        "slope": slope,
        "trend": trend,
        "trend_label": ROE_TREND_LABELS[trend],
        "n_years": n_years,
    }


def compute_coverage_score(row: pd.Series) -> str:
    """
    回傳五點覆蓋度字串，例如 "3/5"。

    目前系統只能自動判斷①②④（淨利部分），③為半自動（僅提供產業分類），
    ⑤完全無法自動判斷。若未來資料補上「董監持股」或「上市年資」欄位，
    可計算項目數會自動增加。
    """
    calculable = COVERAGE_AUTO_ITEMS
    for extra_col in ("董監持股", "上市年資"):
        if extra_col in row.index and pd.notna(row.get(extra_col)):
            calculable += 1
    calculable = min(calculable, COVERAGE_TOTAL)
    return f"{calculable}/{COVERAGE_TOTAL}"
