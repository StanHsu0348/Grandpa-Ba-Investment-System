# -*- coding: utf-8 -*-
"""
台股（twlist.xlsx）SECTOR 欄位的大分類對照表。

台股 SECTOR 已經是中文、只有 35 種，數量本身不算多，但一次攤平列在
multiselect 裡仍不容易掃視。這裡比照美股頁面的做法，額外提供一層大分類，
讓使用者可以先縮小範圍（例如只看「電子科技」），再從細分產業挑選。

若未來 twlist.xlsx 出現新的 SECTOR 字串，`group_of()` 會回退為 "other"
（其他），不會噴錯，但建議之後補上正式分類。
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 大分類（順序即為 UI 呈現順序）
# ---------------------------------------------------------------------------
TW_SECTOR_GROUPS = {
    "tech": "電子科技",
    "materials": "傳產原物料",
    "consumer": "民生消費",
    "agri": "農業",
    "financial": "金融保險",
    "industrial": "工業與運輸",
    "energy_utility": "能源與公用事業",
    "healthcare": "生技醫療",
    "construction": "營建地產",
    "other": "其他",
}

# ---------------------------------------------------------------------------
# 個別 SECTOR -> 大分類代碼
# ---------------------------------------------------------------------------
TW_SECTOR_GROUP_OF: dict[str, str] = {
    "半導體業": "tech",
    "光電業": "tech",
    "其他電子業": "tech",
    "電子零組件業": "tech",
    "電子通路業": "tech",
    "電腦及週邊設備業": "tech",
    "通信網路業": "tech",
    "資訊服務業": "tech",
    "數位雲端": "tech",
    "化學工業": "materials",
    "塑膠工業": "materials",
    "橡膠工業": "materials",
    "水泥工業": "materials",
    "玻璃陶瓷": "materials",
    "鋼鐵工業": "materials",
    "造紙工業": "materials",
    "電器電纜": "materials",
    "紡織纖維": "materials",
    "食品工業": "consumer",
    "貿易百貨業": "consumer",
    "居家生活": "consumer",
    "文化創意業": "consumer",
    "運動休閒": "consumer",
    "觀光事業": "consumer",
    "觀光餐旅": "consumer",
    "農業科技業": "agri",
    "金融保險業": "financial",
    "電機機械": "industrial",
    "汽車工業": "industrial",
    "航運業": "industrial",
    "油電燃氣業": "energy_utility",
    "綠能環保": "energy_utility",
    "生技醫療業": "healthcare",
    "建材營造業": "construction",
    "其他業": "other",
}


def group_of(sector: str) -> str:
    """回傳 SECTOR 所屬的大分類代碼，找不到對照時歸類為 "other"。"""
    return TW_SECTOR_GROUP_OF.get(sector, "other")
