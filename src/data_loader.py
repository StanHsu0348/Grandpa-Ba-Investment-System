# -*- coding: utf-8 -*-
"""
資料讀取與清洗模組
"""
from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS = [
    "Symbol",
    "COMPANY",
    "收盤日",
    "收盤價",
    "貴價",
    "淑價",
    "預期ROE",
    "預期常利",
    "財報幣別",
    "盈再率",
    "預期配息率",
    "ROE1",
    "ROE2",
    "ROE3",
    "ROE4",
    "ROE5",
    "SECTOR",
    # Shares、預期報酬率並非五點原則本身用到的欄位，但 views/tw.py 分別拿來算
    # 市值(億) 與 IRR 篩選，若這裡不驗證，上傳到這兩欄缺漏的檔案會通過
    # load_tw_data() 檢查、卻在畫面渲染時噴出 KeyError（使用者只會看到原生
    # traceback，看不出是缺欄位），所以兩者都必須是必要欄位。
    "Shares",
    "預期報酬率",
]

NUMERIC_COLUMNS = [
    "收盤價",
    "貴價",
    "淑價",
    "預期ROE",
    "預期常利",
    "盈再率",
    "預期配息率",
    "ROE1",
    "ROE2",
    "ROE3",
    "ROE4",
    "ROE5",
    "Shares",
    "預期報酬率",
]


class DataLoadError(Exception):
    """資料讀取或欄位驗證失敗時拋出。"""


def load_tw_data(path_or_buffer) -> pd.DataFrame:
    """
    讀入台股清單 Excel、清洗欄位並回傳標準化後的 DataFrame。

    Parameters
    ----------
    path_or_buffer : str | Path | file-like
        Excel 檔案路徑，或 Streamlit file_uploader 回傳的檔案物件。

    Raises
    ------
    DataLoadError
        當檔案無法讀取，或缺少必要欄位時。
    """
    try:
        df = pd.read_excel(path_or_buffer)
    except Exception as exc:  # noqa: BLE001
        raise DataLoadError(f"無法讀取 Excel 檔案：{exc}") from exc

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise DataLoadError(
            "找不到必要欄位：" + "、".join(f"『{c}』" for c in missing) + "，請確認檔案格式。"
        )

    df = df.copy()

    # SECTOR 欄位補齊空白清理（保留缺值為 NaN，不轉成字串 "nan"）
    df["SECTOR"] = df["SECTOR"].where(df["SECTOR"].isna(), df["SECTOR"].astype(str).str.strip())

    # 數值欄位型別轉換（容錯：非數字轉為 NaN）
    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Symbol 統一轉為字串（避免與代號位數/前導零問題衝突）
    df["Symbol"] = df["Symbol"].astype(str).str.strip()

    return df


REQUIRED_COLUMNS_US = [
    "Symbol",
    "COMPANY",
    "收盤日",
    "收盤價",
    "貴價",
    "淑價",
    "預期ROE",
    "預期常利",
    "財報幣別",
    "盈再率",
    "預期配息率",
    "ROE1",
    "ROE2",
    "ROE3",
    "ROE4",
    "ROE5",
    "SECTOR",
    "Industry",
    "COUNTRY",
    "市值($m)",
    "預期報酬率",
]

NUMERIC_COLUMNS_US = [
    "收盤價",
    "貴價",
    "淑價",
    "預期ROE",
    "預期常利",
    "盈再率",
    "預期配息率",
    "ROE1",
    "ROE2",
    "ROE3",
    "ROE4",
    "ROE5",
    "市值($m)",
    "預期報酬率",
]


def load_us_data(path_or_buffer) -> pd.DataFrame:
    """
    讀入美股清單 Excel（uslist.xlsx）、清洗欄位並回傳標準化後的 DataFrame。

    欄位命名與 twlist.xlsx 相同（同一套工具產生），但美股清單額外提供
    `Industry`、`COUNTRY`、`市值($m)` 等欄位，且 `財報幣別` 並非全為單一幣別
    （USD 之外還有 EUR、JPY、CAD 等多國掛牌／ADR 公司），使用時需注意
    跨幣別金額（例如「預期常利」門檻）不能直接互相比較。

    Parameters
    ----------
    path_or_buffer : str | Path | file-like
        Excel 檔案路徑，或 Streamlit file_uploader 回傳的檔案物件。

    Raises
    ------
    DataLoadError
        當檔案無法讀取，或缺少必要欄位時。
    """
    try:
        df = pd.read_excel(path_or_buffer)
    except Exception as exc:  # noqa: BLE001
        raise DataLoadError(f"無法讀取 Excel 檔案：{exc}") from exc

    missing = [col for col in REQUIRED_COLUMNS_US if col not in df.columns]
    if missing:
        raise DataLoadError(
            "找不到必要欄位：" + "、".join(f"『{c}』" for c in missing) + "，請確認檔案格式。"
        )

    df = df.copy()

    for col in ("SECTOR", "Industry", "COUNTRY", "財報幣別"):
        df[col] = df[col].where(df[col].isna(), df[col].astype(str).str.strip())
        df[col] = df[col].replace("", pd.NA)

    for col in NUMERIC_COLUMNS_US:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["Symbol"] = df["Symbol"].astype(str).str.strip()

    return df


def get_data_date(df: pd.DataFrame) -> str:
    """回傳資料日期（收盤日欄位最大值），格式化為 YYYY-MM-DD 字串。"""
    if "收盤日" not in df.columns or df["收盤日"].dropna().empty:
        return "未知"
    max_date = int(df["收盤日"].dropna().max())
    date_str = str(max_date)
    if len(date_str) == 8:
        return f"{date_str[0:4]}-{date_str[4:6]}-{date_str[6:8]}"
    return date_str
