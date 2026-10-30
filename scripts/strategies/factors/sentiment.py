"""情绪因子（v1.26 阶段 1）：个股级情绪强度打分。

与市场级情绪指数（`technical/sentiment.py` 的 `SentimentCalculator`）的区别：
后者对全市场输出同一个值，本因子**按个股**输出，横截面上有区分度——
这正是它能作为 screener 因子的前提。

四个子项（口径与档位见 docs/design/sentiment-factor-design.md，
封单占比与炸板次数档位按 2026-10-30 实测分布校准）：

| 子项 | 权重 | 来源字段 |
| --- | --- | --- |
| 连板高度 | 0.30 | lbc |
| 封板质量 | 0.25 | zbc / fund / ltsz |
| 板块热度 | 0.25 | hybk（行业板块）|
| 活跃度 | 0.20 | hs（换手率）|

缺失语义：该股不在涨停/炸板池 → 返回 None（缺失，不是 0 分），
由归一化层按中性 50 分位处理；池内个股的个别子项缺失 → 该子项按中性 50 计。
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 子项权重（合计 1.0）
W_HEIGHT = 0.30
W_SEAL = 0.25
W_SECTOR = 0.25
W_ACTIVITY = 0.20

# 单项缺失时的中性值
NEUTRAL = 50.0


def _lbc_score(lbc: int | None) -> float:
    """连板高度分：首板 40，每多一板递增但边际递减（高位连板已透支涨幅）。

    lbc_score = 40 + 45 × (1 − 0.5^(lbc−1))
        lbc=1 → 40.00    lbc=2 → 62.50    lbc=3 → 73.75    lbc=4 → 79.38    lbc=5 → 82.19
    增幅 22.5 / 11.25 / 5.63 / 2.81 —— 逐板递减。
    炸板股无 lbc（从未封板）→ 中性 50（不享首板的情绪强度）。
    """
    if not lbc or lbc < 1:
        return NEUTRAL
    return round(40 + 45 * (1 - 0.5 ** (lbc - 1)), 2)


def _broken_score(zbc: int | None) -> float:
    """炸板次数分（实测 n=64 分布：0→15, 1→18, 2→13, 3~5→10, ≥6→8）。

    炸板次数反映"封不住"的程度，是情绪质量的核心负向信号。
    """
    if zbc is None:
        return NEUTRAL
    if zbc <= 0:
        return 100.0
    if zbc == 1:
        return 75.0
    if zbc == 2:
        return 55.0
    if zbc <= 5:
        return 35.0
    return 20.0


def _seal_ratio_score(ratio_pct: float | None) -> float:
    """封单强度分：封单额占流通市值（%）。

    档位按实测分位重设（p50=0.22%、p75=1.36%、p90=3.47%）：
    0 → 30；<0.1% → 50；<0.5% → 70；<2% → 85；≥2% → 100
    ratio 为 None（数据缺失）→ 中性 50，**不当作"没有封单"**。
    """
    if ratio_pct is None:
        return NEUTRAL
    if ratio_pct <= 0:
        return 30.0
    if ratio_pct < 0.1:
        return 50.0
    if ratio_pct < 0.5:
        return 70.0
    if ratio_pct < 2.0:
        return 85.0
    return 100.0


def _seal_score(entry: dict) -> float:
    """封板质量分 = 0.6 × 炸板分 + 0.4 × 封单强度分。"""
    fund = entry.get("fund")
    ltsz = entry.get("ltsz")
    ratio_pct = None
    if fund is not None and ltsz:
        ratio_pct = fund / ltsz * 100
    return round(0.6 * _broken_score(entry.get("zbc")) + 0.4 * _seal_ratio_score(ratio_pct), 2)


def _sector_strength_score(share_pct: float | None) -> float:
    """板块热度分（当日强度）：该板块涨停家数占全市场涨停家数的比例（%）。

    用占比而非绝对家数——绝对家数随市场情绪总量波动（冰点 20 家 vs 亢奋 100 家），
    占比在不同市场状态下可比。

    0 → 30；<3% → 55；<8% → 72；<15% → 88；≥15% → 100
    """
    if share_pct is None:
        return NEUTRAL
    if share_pct <= 0:
        return 30.0
    if share_pct < 3:
        return 55.0
    if share_pct < 8:
        return 72.0
    if share_pct < 15:
        return 88.0
    return 100.0


def _sector_rotation_bonus(sector: str, snapshot: dict) -> float:
    """板块轮动加分：近 5 日涨停家数均值 vs 前 5 日均值的环比。

    环比 > 1.5 → +15；1.0~1.5 → +8；< 1.0 → 0
    历史不足（< 10 个交易日快照）→ 0（不做时序比较）。
    """
    from data.sentiment_panel import get_history

    history = get_history(days=11)
    if len(history) < 10:
        return 0.0

    def _count(snap: dict) -> int:
        agg = (snap.get("sectors") or {}).get(sector) or {}
        return int(agg.get("limit_up", 0) or 0)

    recent = [_count(s) for s in history[-5:]]
    earlier = [_count(s) for s in history[-10:-5]]
    recent_avg = sum(recent) / len(recent)
    earlier_avg = sum(earlier) / len(earlier)
    if earlier_avg <= 0:
        return 0.0
    ratio = recent_avg / earlier_avg
    if ratio > 1.5:
        return 15.0
    if ratio >= 1.0:
        return 8.0
    return 0.0


def _activity_score(hs: float | None) -> float:
    """活跃度分（换手率 %）：过低=无人问津，过高=接力风险（非单调）。

    <1% → 30；1~5% → 55；5~15% → 85；15~30% → 70；≥30% → 45
    """
    if hs is None:
        return NEUTRAL
    if hs < 1:
        return 30.0
    if hs < 5:
        return 55.0
    if hs < 15:
        return 85.0
    if hs < 30:
        return 70.0
    return 45.0


def sentiment_score(code: str) -> float | None:
    """个股情绪强度分（0-100），用**最新**快照。

    实时路径（screener）用本函数；回测路径必须用 `sentiment_score_at`，
    否则会把今天的情绪用在历史时点上——未来函数。

    Args:
        code: 股票代码（sh/sz/bj 前缀或裸代码均可）

    Returns:
        0-100 分值；该股不在涨停/炸板池（无情绪数据）时返回 None（缺失，非 0）
    """
    from data.sentiment_panel import get_latest_snapshot

    return _score_with_snapshot(code, get_latest_snapshot())


def sentiment_score_at(code: str, date: str) -> float | None:
    """个股情绪强度分（0-100），用**指定日期**的快照（回测路径）。

    Args:
        code: 股票代码
        date: 交易日 YYYYMMDD

    Returns:
        0-100 分值；该日无快照或该股不在池内时返回 None
    """
    from data.sentiment_panel import get_snapshot

    return _score_with_snapshot(code, get_snapshot(date))


def _score_with_snapshot(code: str, snapshot: Optional[dict]) -> float | None:
    """按给定快照计算情绪分（快照为 None → 缺失）。"""
    from data.sentiment_panel import get_sector_heat, get_stock_sentiment

    if not snapshot:
        return None
    entry = get_stock_sentiment(code, snapshot=snapshot)
    if not entry:
        return None

    # 板块热度：板块涨停家数占比 + 轮动加分
    heat_map = get_sector_heat(snapshot)
    sector = entry.get("sector") or ""
    base_sector = _sector_strength_score(heat_map.get(sector))
    bonus = _sector_rotation_bonus(sector, snapshot) if sector else 0.0
    sector_score = min(100.0, base_sector + bonus)

    total = (
        W_HEIGHT * _lbc_score(entry.get("lbc"))
        + W_SEAL * _seal_score(entry)
        + W_SECTOR * sector_score
        + W_ACTIVITY * _activity_score(entry.get("hs"))
    )
    return round(total, 2)


def sentiment_details(code: str) -> dict | None:
    """情绪因子的分项明细（供报告/调试展示）。

    Args:
        code: 股票代码

    Returns:
        {"score": float, "components": {...}, "entry": {...}}；无数据时返回 None
    """
    from data.sentiment_panel import get_latest_snapshot, get_sector_heat, get_stock_sentiment

    snapshot = get_latest_snapshot()
    if not snapshot:
        return None
    entry = get_stock_sentiment(code, snapshot=snapshot)
    if not entry:
        return None

    heat_map = get_sector_heat(snapshot)
    sector = entry.get("sector") or ""
    base_sector = _sector_strength_score(heat_map.get(sector))
    bonus = _sector_rotation_bonus(sector, snapshot) if sector else 0.0
    sector_score = min(100.0, base_sector + bonus)

    components = {
        "height": _lbc_score(entry.get("lbc")),
        "seal": _seal_score(entry),
        "sector": sector_score,
        "activity": _activity_score(entry.get("hs")),
    }
    total = (
        W_HEIGHT * components["height"]
        + W_SEAL * components["seal"]
        + W_SECTOR * components["sector"]
        + W_ACTIVITY * components["activity"]
    )
    return {
        "score": round(total, 2),
        "components": components,
        "sector_rotation_bonus": bonus,
        "entry": entry,
    }


__all__ = ["sentiment_score", "sentiment_score_at", "sentiment_details"]
