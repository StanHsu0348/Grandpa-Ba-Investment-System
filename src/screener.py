# -*- coding: utf-8 -*-
"""
五點原則篩選邏輯（純函式）
"""
from __future__ import annotations

from typing import Literal, Optional, Sequence

import numpy as np
import pandas as pd

from .constants import ROE_COLS_RECENT_TO_OLD, ROE_RECENT_3_COLS
from .scoring import compute_roe_stability_bulk

ROE_MODES = ("A", "B", "C", "D", "E")

ROE_MODE_LABELS = {
    "A": "A. 嚴格版（近5年每年皆達標）",
    "B": "B. 近3年版",
    "C": "C. 平均版",
    "D": "D. 預估值版",
    "E": "E. 趨勢版（一致向上／持平）",
}


def roe_pass_mask(df: pd.DataFrame, mode: str, threshold: float) -> pd.Series:
    """回傳單一 ROE 篩選模式的布林遮罩（True=符合）。"""
    if mode == "A":
        # 嚴格版：5 年皆需有值且皆 >= 門檻，缺值視為不通過
        sub = df[ROE_COLS_RECENT_TO_OLD]
        return (sub >= threshold).all(axis=1) & sub.notna().all(axis=1)

    if mode == "B":
        # 近 3 年版：以可用年數計算最小值，全缺才不通過
        sub = df[ROE_RECENT_3_COLS]
        has_any = sub.notna().any(axis=1)
        min_val = sub.min(axis=1, skipna=True)
        return has_any & (min_val >= threshold)

    if mode == "C":
        # 平均版：以可用年數計算平均值
        sub = df[ROE_COLS_RECENT_TO_OLD]
        has_any = sub.notna().any(axis=1)
        mean_val = sub.mean(axis=1, skipna=True)
        return has_any & (mean_val >= threshold)

    if mode == "D":
        return df["預期ROE"] >= threshold

    if mode == "E":
        # 用向量化版本（見 scoring.compute_roe_stability_bulk）取代逐列
        # df.apply + np.polyfit，這裡是側邊欄即時計數的效能瓶頸來源
        # （美股 12,497 列，逐列版本約 1.2 秒／次，向量化後降到毫秒級）。
        trend = compute_roe_stability_bulk(df)["trend"]
        sub = df[ROE_COLS_RECENT_TO_OLD]
        mean_val = sub.mean(axis=1, skipna=True)
        has_any = sub.notna().any(axis=1)
        return has_any & trend.isin(["up", "flat"]) & (mean_val >= threshold)

    raise ValueError(f"未知的 ROE 模式：{mode}")


def filter_by_roe(df: pd.DataFrame, modes: Sequence[str], threshold: float) -> pd.DataFrame:
    """
    依選定的 ROE 模式（可複選，複選時為 AND 條件）與門檻篩選。
    modes 為空 list 時不套用 ROE 篩選，直接回傳原 df。
    """
    if not modes:
        return df
    mask = pd.Series(True, index=df.index)
    for mode in modes:
        mask &= roe_pass_mask(df, mode, threshold)
    return df[mask]


def filter_by_payout(df: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """原則②：配息率 >= 門檻。threshold=0 視為不限（不過濾缺值以外的資料）。"""
    if threshold <= 0:
        return df
    return df[df["預期配息率"] >= threshold]


def filter_by_net_income(df: pd.DataFrame, threshold: Optional[float]) -> pd.DataFrame:
    """原則④（淨利部分）：預期常利 >= 門檻。threshold 為 None 或 <=0 視為不限。"""
    if threshold is None or threshold <= 0:
        return df
    return df[df["預期常利"] >= threshold]


def filter_by_sector(df: pd.DataFrame, sectors: Optional[Sequence[str]]) -> pd.DataFrame:
    """依產業類別（SECTOR）篩選。sectors 為 None 或空 list 視為不限（全選）。"""
    if not sectors:
        return df
    return df[df["SECTOR"].isin(sectors)]


ValuationMode = Literal["any", "cheap", "fair", "expensive"]


def filter_by_valuation(df: pd.DataFrame, mode: ValuationMode = "any") -> pd.DataFrame:
    """
    加分項：估價區間篩選（依『貴價』／『淑價』欄位）。
    - cheap: 收盤價 <= 淑價
    - fair: 淑價 < 收盤價 < 貴價
    - expensive: 收盤價 >= 貴價
    - any: 不篩選
    缺值（無淑價/貴價資料）一律排除在 cheap/fair/expensive 篩選結果之外。
    """
    if mode == "any":
        return df

    has_valuation = df["貴價"].notna() & df["淑價"].notna() & df["收盤價"].notna()
    sub = df[has_valuation]

    if mode == "cheap":
        return sub[sub["收盤價"] <= sub["淑價"]]
    if mode == "fair":
        return sub[(sub["收盤價"] > sub["淑價"]) & (sub["收盤價"] < sub["貴價"])]
    if mode == "expensive":
        return sub[sub["收盤價"] >= sub["貴價"]]

    raise ValueError(f"未知的估價模式：{mode}")


def filter_by_irr(df: pd.DataFrame, threshold: Optional[float]) -> pd.DataFrame:
    """
    加分項：預期報酬率（IRR，對應課程 Ch6 合理買價報酬率概念）>= 門檻。
    threshold=None 視為不套用此篩選。套用時，缺值（無法估算 IRR 的公司）一律排除。
    """
    if threshold is None:
        return df
    return df[df["預期報酬率"] >= threshold]


def apply_all_filters(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    串接所有篩選函式。

    params 支援的 key：
        roe_modes: list[str]           -- 選定的 ROE 模式（可複選）
        roe_threshold: float
        payout_threshold: float
        net_income_threshold: float | None
        sectors: list[str] | None
        valuation_mode: "any"|"cheap"|"fair"|"expensive"
        irr_threshold: float | None
    """
    result = df
    result = filter_by_roe(
        result, params.get("roe_modes", []), params.get("roe_threshold", 0.0)
    )
    result = filter_by_payout(result, params.get("payout_threshold", 0.0))
    result = filter_by_net_income(result, params.get("net_income_threshold"))
    result = filter_by_sector(result, params.get("sectors"))
    result = filter_by_valuation(result, params.get("valuation_mode", "any"))
    result = filter_by_irr(result, params.get("irr_threshold"))
    return result
