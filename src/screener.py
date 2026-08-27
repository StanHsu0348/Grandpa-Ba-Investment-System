# -*- coding: utf-8 -*-
"""
五點原則篩選邏輯（純函式）
"""
from __future__ import annotations

from typing import Literal, Optional, Sequence

import pandas as pd

from .constants import ROE_COLS_RECENT_TO_OLD


def filter_by_roe(df: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """
    原則①：5 年 ROE 穩定度篩選。

    規則：近 5 年（ROE1~ROE5，實際歷史值，非預期ROE）任一年低於門檻就排除；
    缺值視為不通過（無法確認該年度是否達標）。threshold<=0 視為不限，
    與 filter_by_payout()／filter_by_net_income() 的「0=不限」慣例一致。

    這裡刻意只用一套規則，不提供「近3年版」「平均版」「用預期ROE篩選」等
    其他寬鬆模式——早期版本曾經做過 5 種可複選模式＋共用門檻的設計，
    但門檻本身不會自動生效，必須額外勾選對應模式才套用篩選，容易讓人
    誤以為「設定門檻」就等於「篩選生效」。改成單一規則後，設定門檻就
    直接套用，不需要額外的模式選擇步驟。
    """
    if threshold <= 0:
        return df
    sub = df[ROE_COLS_RECENT_TO_OLD]
    mask = (sub >= threshold).all(axis=1) & sub.notna().all(axis=1)
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


def _has_valid_valuation(df: pd.DataFrame) -> pd.Series:
    """判斷是否有可用的估價資料（貴價／淑價／收盤價皆非缺值，且貴價／淑價 > 0）。

    貴價／淑價 <= 0 視為無資料：實測美股清單中極低價股票（多為 <$0.1 的
    細價股）常見『貴價』『淑價』其中一項或兩項恰為 0（例如貴價=0.1、
    淑價=0.0），研判是資料源對極小數值四捨五入到顯示精度的副作用，而非
    真的估出「合理買價下限是 0」，若不排除，這些股票會被收盤價（同樣是
    正數的細價股價格）大於等於 0 的「貴價」而誤判為『昂貴價』。

    filter_by_valuation() 與 valuation_labels() 共用這個判斷，確保篩選
    邏輯與畫面上顯示的『估價區間』欄位對同一批資料的認定完全一致。
    """
    return (
        df["貴價"].notna() & df["淑價"].notna() & df["收盤價"].notna()
        & (df["貴價"] > 0) & (df["淑價"] > 0)
    )


def filter_by_valuation(df: pd.DataFrame, mode: ValuationMode = "any") -> pd.DataFrame:
    """
    加分項：估價區間篩選（依『貴價』／『淑價』欄位）。
    - cheap: 收盤價 <= 淑價
    - fair: 淑價 < 收盤價 < 貴價
    - expensive: 收盤價 >= 貴價
    - any: 不篩選
    缺值（無淑價/貴價資料，或貴價/淑價 <= 0，見 _has_valid_valuation()）
    一律排除在 cheap/fair/expensive 篩選結果之外。
    """
    if mode == "any":
        return df

    sub = df[_has_valid_valuation(df)]

    if mode == "cheap":
        return sub[sub["收盤價"] <= sub["淑價"]]
    if mode == "fair":
        return sub[(sub["收盤價"] > sub["淑價"]) & (sub["收盤價"] < sub["貴價"])]
    if mode == "expensive":
        return sub[sub["收盤價"] >= sub["貴價"]]

    raise ValueError(f"未知的估價模式：{mode}")


def valuation_labels(df: pd.DataFrame) -> pd.Series:
    """
    回傳整個 DataFrame 每列的估價區間標籤：便宜價／合理價／昂貴價／無法估價。

    原本 views/tw.py、views/us.py 各自用 display_df.apply(row 函式) 算這欄，
    兩份程式碼幾乎一樣、判斷邊界卻各自維護，容易改一邊漏改另一邊（就是
    「貴價/淑價<=0 誤判昂貴價」這個 bug 原本的成因之一）。統一成這裡的
    向量化版本後，兩個頁面共用同一份判斷邏輯，也和 filter_by_valuation()
    共用同一個「有效估價資料」定義（_has_valid_valuation()）。
    """
    has_valuation = _has_valid_valuation(df)
    cheap = has_valuation & (df["收盤價"] <= df["淑價"])
    expensive = has_valuation & ~cheap & (df["收盤價"] >= df["貴價"])
    fair = has_valuation & ~cheap & ~expensive

    labels = pd.Series("無法估價", index=df.index)
    labels[fair] = "合理價"
    labels[cheap] = "便宜價"
    labels[expensive] = "昂貴價"
    return labels


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
        roe_threshold: float
        payout_threshold: float
        net_income_threshold: float | None
        sectors: list[str] | None
        valuation_mode: "any"|"cheap"|"fair"|"expensive"
        irr_threshold: float | None
    """
    result = df
    result = filter_by_roe(result, params.get("roe_threshold", 0.0))
    result = filter_by_payout(result, params.get("payout_threshold", 0.0))
    result = filter_by_net_income(result, params.get("net_income_threshold"))
    result = filter_by_sector(result, params.get("sectors"))
    result = filter_by_valuation(result, params.get("valuation_mode", "any"))
    result = filter_by_irr(result, params.get("irr_threshold"))
    return result
