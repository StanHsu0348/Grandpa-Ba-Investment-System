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

    # uslist.xlsx 剛好也具備 REQUIRED_COLUMNS 的全部欄位（同一套工具產生，
    # 美股清單只是「多」欄位），單靠「缺欄位就擋」不夠，會讓台股頁悄悄吃下
    # 美股清單、用台股口徑（市值單位億元台幣、MOPS 查證連結…）算出一堆
    # 錯誤數字卻不報錯。用美股清單獨有欄位反向擋下。
    us_only_cols = [c for c in ("Industry", "COUNTRY", "市值($m)") if c in df.columns]
    if us_only_cols:
        raise DataLoadError(
            "這個檔案看起來是美股清單（含" + "、".join(f"『{c}』" for c in us_only_cols)
            + "欄位），請改在美股頁面上傳，或確認檔案格式。"
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
    """回傳資料日期（收盤日欄位最大值），格式化為 YYYY-MM-DD 字串。

    「收盤日」欄位不在 NUMERIC_COLUMNS 裡強制轉型，保留 pd.read_excel 讀出來
    的原始型別，實務上看過／可能遇到的樣態包括：數字 20260826（目前
    twlist.xlsx／uslist.xlsx 的格式）、pandas Timestamp（儲存格若設成 Excel
    日期格式，會直接讀成 datetime，例如美股清單裡就混著這種列，見
    uslist.xlsx 抽樣資料）、或字串 "2026-08-26"。原本的 int(max_date) 對
    Timestamp／字串都會直接拋 TypeError／ValueError，讓整頁噴原生
    traceback；這裡的資料日期只是輔助顯示，不值得為了格式意外讓整頁掛掉，
    所以改成逐型別判斷＋保底 try/except，失敗一律回傳「未知」。
    """
    if "收盤日" not in df.columns:
        return "未知"
    values = df["收盤日"].dropna()
    if values.empty:
        return "未知"

    try:
        max_date = values.max()
    except TypeError:
        return "未知"

    if hasattr(max_date, "strftime"):  # pandas Timestamp / datetime.date 等
        return max_date.strftime("%Y-%m-%d")

    try:
        date_str = str(int(max_date)) if isinstance(max_date, (int, float)) else str(max_date).strip()
    except (TypeError, ValueError):
        return "未知"

    if len(date_str) == 8 and date_str.isdigit():
        return f"{date_str[0:4]}-{date_str[4:6]}-{date_str[6:8]}"
    return date_str or "未知"
