# -*- coding: utf-8 -*-
"""
巴菲特「五點好企業原則」選股系統 — 常數設定
"""

# ---------------------------------------------------------------------------
# ROE 欄位時間順序（Phase 1 前置確認結論）
#
# 以台積電(2330)實際資料交叉比對公開資訊後判斷：
#   ROE1 = 最近一年度，ROE5 = 五年前（由近到遠遞減）
#
# 判斷依據：twlist.xlsx 中 2330 的 ROE4 = 46.9%，是五欄中最高值；
# 多個公開資料源（wantgoo、moneydj 及台積電歷年財報公開數字）皆顯示
# 2022 年是台積電近年 ROE 的高峰。本資料收盤日最新為 2026-08-25，
# 若 ROE1 對應最近完整年度（約 2025 年）往回推 4 年，正好落在 2022 年，
# 與「ROE4 是最高值」吻合，故採此順序。
#
# 註：不同資料源 ROE 計算口徑（期末權益 vs 平均權益等）略有差異，
# 此判斷信心並非 100%，如未來取得更明確的資料欄位定義，
# 請更新以下常數並重新驗證 tests/test_screener.py。
# ---------------------------------------------------------------------------
ROE_MOST_RECENT_COL = "ROE1"
ROE_OLDEST_COL = "ROE5"
ROE_COLS_RECENT_TO_OLD = ["ROE1", "ROE2", "ROE3", "ROE4", "ROE5"]  # 近→遠
ROE_RECENT_3_COLS = ["ROE1", "ROE2", "ROE3"]  # 近 3 年

# 5年 ROE 趨勢圖的 x 軸標籤、下載表格展開欄位名稱共用同一份，順序為「舊→新」
# （對應 reversed(ROE_COLS_RECENT_TO_OLD)），台股／美股頁面都用得到。
ROE_YEAR_LABELS_OLD_TO_NEW = ["5年前", "4年前", "3年前", "2年前", "最近一年"]

# ---------------------------------------------------------------------------
# 篩選門檻預設值
# ---------------------------------------------------------------------------
DEFAULT_ROE_THRESHOLD = 15.0          # 原則① ROE 門檻（%）
DEFAULT_PAYOUT_THRESHOLD = 40.0       # 原則② 配息率門檻（%）
DEFAULT_NET_INCOME_THRESHOLD = 500.0  # 原則④ 淨利門檻（百萬元，5億）
DEFAULT_IRR_THRESHOLD = 15.0          # 延伸判準：合理買價報酬率 IRR 門檻（%）

PAYOUT_QUICK_OPTIONS = {
    ">20%": 20.0,
    ">40%": 40.0,
    ">60%": 60.0,
    "不限": 0.0,
}

NET_INCOME_QUICK_OPTIONS = {
    "≥100": 100.0,
    "≥500 (5億)": 500.0,
    "≥1000": 1000.0,
    "不限": 0.0,
}

# IRR 篩選滑桿邊界。下界刻意設在資料實際最小值（約 -51%）之下，
# 讓「滑到底」等同「不限」，維持與配息率／淨利門檻「0=不限」一致的慣例。
IRR_SLIDER_MIN = -60.0
IRR_SLIDER_MAX = 60.0

IRR_QUICK_OPTIONS = {
    "≥15% (課程門檻)": DEFAULT_IRR_THRESHOLD,
    "不限": IRR_SLIDER_MIN,
}

# ---------------------------------------------------------------------------
# 提示文字
# ---------------------------------------------------------------------------
MANUAL_CHECK_NOTE = "董監持股與上市年資需自行至公開資訊觀測站查證"

MOPS_URL_TEMPLATE = "https://mops.twse.com.tw/mops/web/t51sb01?TYPEK=sii&co_id={symbol}"

ROE_TREND_LABELS = {
    "up": "一致向上",
    "flat": "持平",
    "down": "由高往下",
    "volatile": "忽高忽低",
    "insufficient": "資料不足",
}

# 五點原則中，目前系統可自動判斷的項目數（①②④淨利部分）
COVERAGE_TOTAL = 5
COVERAGE_AUTO_ITEMS = 3

# ---------------------------------------------------------------------------
# 美股（uslist.xlsx）專屬設定
#
# 欄位命名與 twlist.xlsx 相同（同一套工具產生），ROE1~ROE5 沿用台股已確認的
# 「近→遠」順序假設（ROE1=最近一年，ROE5=五年前）。此假設尚未針對美股個別
# 交叉比對驗證，信心程度與台股相同（見上方 ROE_MOST_RECENT_COL 註解）。
# ---------------------------------------------------------------------------
DEFAULT_ROE_THRESHOLD_US = 15.0        # 原則① ROE 門檻（%），與台股課程門檻一致
DEFAULT_PAYOUT_THRESHOLD_US = 40.0     # 原則② 配息率門檻（%）
# 原則④ 淨利門檻：改用課程附錄「稅前淨利國際級 > USD 75M」延伸判準
# （單位：百萬美元，美股體質差異極大，不沿用台股 5億元台幣的門檻數字）
DEFAULT_NET_INCOME_THRESHOLD_US = 75.0
DEFAULT_IRR_THRESHOLD_US = 15.0        # 延伸判準：合理買價報酬率 IRR 門檻（%）

PAYOUT_QUICK_OPTIONS_US = dict(PAYOUT_QUICK_OPTIONS)

NET_INCOME_QUICK_OPTIONS_US = {
    "≥75 (國際級)": DEFAULT_NET_INCOME_THRESHOLD_US,
    "≥500": 500.0,
    "≥1000": 1000.0,
    "不限": 0.0,
}

IRR_QUICK_OPTIONS_US = {
    "≥15% (課程門檻)": DEFAULT_IRR_THRESHOLD_US,
    "不限": IRR_SLIDER_MIN,
}

MANUAL_CHECK_NOTE_US = "上市年資與內部人（董監）持股需自行至 SEC EDGAR（sec.gov）或 Yahoo Finance 等公開資料源查證。"

# 美股橫跨多國掛牌／ADR，公開資訊來源不像台股 MOPS 有單一入口，
# 統一導向 Yahoo Finance 個股頁面作為查證起點。
YAHOO_FINANCE_URL_TEMPLATE = "https://finance.yahoo.com/quote/{symbol}"

CURRENCY_CAVEAT_NOTE = (
    "美股清單涵蓋多國掛牌公司，「財報幣別」並非全部是 USD（也有 EUR、JPY、CAD 等），"
    "淨利門檻是用各公司原始財報幣別的數值直接比較，並未換算成統一幣別，"
    "跨幣別比較金額時請特別留意「財報幣別」欄位。"
)
