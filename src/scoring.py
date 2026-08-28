# -*- coding: utf-8 -*-
"""
ROE 穩定度評分、五點覆蓋度計算
"""
from __future__ import annotations

import itertools

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
    計算一列資料的 5 年 ROE 穩定度指標（單列版本，供個股詳細卡片使用）。

    內部直接複用向量化版本 compute_roe_stability_bulk()（把單列包成
    一個 1 列的 DataFrame 傳進去），而不是另外維護一套邏輯。原因：
    早期這裡曾經另外寫一套用 np.polyfit 算斜率的邏輯，數學上與
    compute_roe_stability_bulk() 的 OLS 公式等價，但兩種算法在浮點數
    層級的捨入誤差不同——當真實斜率剛好落在 FLAT_SLOPE_THRESHOLD（1.0）
    這類分類門檻正上面時（例如 slope 理論值精確為 1.0，一套算出
    0.9999999999999989、另一套算出 1.0000000000000007），會讓同一檔
    股票被分到不同的趨勢類別。實測美股 12,497 筆資料裡曾出現 9 筆這種
    邊界案例（見 tests/test_scoring_bulk.py）。統一成同一個實作可以從
    根本消除這個不一致，而不是繼續維護兩套「數學等價、數值不等價」的
    算法。

    回傳 dict：
        std: 標準差（可用年度）
        slope: 線性回歸斜率（每年變化的百分點，時間由舊到新）
        trend: 趨勢分類代碼（up/flat/down/volatile/insufficient）
        trend_label: 趨勢分類中文標籤
        n_years: 可用（非缺值）年度數
    """
    result = compute_roe_stability_bulk(pd.DataFrame([row])).iloc[0]
    return {
        "std": result["std"],
        "slope": result["slope"],
        "trend": result["trend"],
        "trend_label": result["trend_label"],
        "n_years": int(result["n_years"]),
    }


def compute_roe_stability_bulk(df: pd.DataFrame) -> pd.DataFrame:
    """
    一次計算整個 DataFrame 的 5 年 ROE 穩定度指標（向量化版本）。

    這是 compute_roe_stability() 唯一的實作邏輯所在（見上方函式的說明）。
    寫成向量化是為了解決效能問題：逐列 df.apply + 每列一次 np.polyfit，
    在美股 12,497 列的資料上約需 1.2 秒；改成整批 numpy 陣列運算後，
    降到毫秒等級。目前每次呼叫都是透過 compute_roe_stability() 包成
    1 列 DataFrame 使用（個股詳細卡片的趨勢圖說明文字），但保留向量化
    寫法是為了未來若有需要一次算整批資料（例如趨勢分類要拿來做篩選）
    時可以直接複用，不必重寫。

    數學設計：
    - slope：用標準 OLS 斜率公式
      slope = (n·Σxy − Σx·Σy) / (n·Σx² − (Σx)²)
      x 只用「該列實際有值」的欄位位置（缺值位置的 x 也視為缺值一併排除），
      藉此在整批矩陣運算裡跳過每列各自不同數量的有效點。
    - std：用 nansum 算 population variance（Σ(y-ȳ)²/n），對應
      np.std()（預設 ddof=0）。
    - 單調性（monotonic_up/down）：檢查「所有位置組合 (i<j)」的差是否
      同向，而非只看「有值年度依序排列後、壓縮掉缺值的相鄰兩點」。
      對一個依時間排序的數列而言，兩種判斷法數學上等價（遞移律），
      但前者不需要先找出「壓縮後的相鄰值」，只要用位置遮罩即可整批
      算出，適合向量化。
    """
    cols_old_to_new = list(reversed(ROE_COLS_RECENT_TO_OLD))
    y = df[cols_old_to_new].to_numpy(dtype=float)
    n_rows, n_cols = y.shape

    valid = ~np.isnan(y)
    n_years = valid.sum(axis=1)
    n = n_years.astype(float)

    x = np.where(valid, np.arange(n_cols, dtype=float), np.nan)

    with np.errstate(invalid="ignore", divide="ignore"):
        sum_x = np.nansum(x, axis=1)
        sum_y = np.nansum(y, axis=1)
        sum_xy = np.nansum(x * y, axis=1)
        sum_x2 = np.nansum(x * x, axis=1)
        denom = n * sum_x2 - sum_x**2
        slope = (n * sum_xy - sum_x * sum_y) / denom

        mean_y = sum_y / n
        var_y = np.nansum((y - mean_y[:, None]) ** 2, axis=1) / n
        std = np.sqrt(var_y)

    monotonic_up = np.ones(n_rows, dtype=bool)
    monotonic_down = np.ones(n_rows, dtype=bool)
    for i, j in itertools.combinations(range(n_cols), 2):
        both_valid = valid[:, i] & valid[:, j]
        diff = y[:, j] - y[:, i]
        monotonic_up &= ~(both_valid & (diff < -1e-9))
        monotonic_down &= ~(both_valid & (diff > 1e-9))

    insufficient = n_years < 2
    up = ~insufficient & monotonic_up & (slope > TREND_SLOPE_THRESHOLD)
    down = ~insufficient & ~up & monotonic_down & (slope < -TREND_SLOPE_THRESHOLD)
    flat = ~insufficient & ~up & ~down & (std < FLAT_STD_THRESHOLD) & (np.abs(slope) < FLAT_SLOPE_THRESHOLD)
    volatile = ~insufficient & ~up & ~down & ~flat

    trend = np.full(n_rows, "insufficient", dtype=object)
    trend[up] = "up"
    trend[down] = "down"
    trend[flat] = "flat"
    trend[volatile] = "volatile"

    return pd.DataFrame(
        {
            "std": np.where(insufficient, np.nan, std),
            "slope": np.where(insufficient, np.nan, slope),
            "trend": trend,
            "trend_label": [ROE_TREND_LABELS[t] for t in trend],
            "n_years": n_years,
        },
        index=df.index,
    )


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
