"""市场级情绪 → 因子 overlay multiplier（v1.26 阶段 3）。

背景：regime 的 6 态判定（bull/bear/range/panic…）是**粗粒度**的，而市场情绪
是连续量。overlay 的 multiplier 按 regime 查表（离散），无法表达"封板率从 55%
掉到 40%"这种变化。

本模块提供第 5 层叠加：市场级情绪指标（封板率 / 晋级率 / 连板高度 / 板块集中度）
→ 因子 multiplier 细调。

**与个股级 sentiment 因子的分工**：
- 个股级（`strategies/factors/sentiment.py`）→ 因子，横截面区分度，衡量"这只股"
- 市场级（本模块）→ overlay 权重调节，无区分度，衡量"现在这个市场"

**重要**：本模块只做纯计算（不取数、不写盘），输入是已算好的指标 dict，
由调用方决定何时取数。阈值目前基于领域经验设定，**待快照样本积累后校准**
（校准前默认不启用——overlay 的 `sentiment_multipliers` 传 None 即不生效）。
"""

from __future__ import annotations

from typing import Optional

# ── 阈值（待样本校准）──────────────────────────────
# 封板率 = 涨停 / (涨停 + 炸板)：反映资金承接强度
SEAL_RATE_ICE = 0.50  # 低于此值视为情绪冰点
SEAL_RATE_HOT = 0.75  # 高于此值视为情绪亢奋（需同时满足连板高度条件）
# 晋级率 = 昨日涨停股今日涨停比例
PROMOTION_ICE = 0.20  # 低于此值视为情绪冰点
# 连板高度（元凶信号）：高度越高，赚钱效应越极端
HOT_MAX_HEIGHT = 6
# 板块集中度（top3 板块涨停家数占比）：越高说明资金越拥挤
HOT_SECTOR_CONCENTRATION = 0.35


def market_sentiment_metrics(snapshot: Optional[dict], promotion_rate: Optional[float] = None) -> dict:
    """从情绪面板快照算市场级情绪指标。

    Args:
        snapshot: 情绪面板快照（None → 空指标）
        promotion_rate: 晋级率（需历史快照；调用方传入以避免重复读盘）

    Returns:
        {
            "seal_rate": float | None,        # 封板率 ∈ [0, 1]
            "promotion_rate": float | None,   # 晋级率 ∈ [0, 1]
            "max_height": int | None,        # 最高连板
            "sector_concentration": float | None,  # top3 板块涨停占比 ∈ [0, 1]
            "limit_up_count": int,
            "broken_count": int,
        }
    """
    if not snapshot:
        return {
            "seal_rate": None,
            "promotion_rate": promotion_rate,
            "max_height": None,
            "sector_concentration": None,
            "limit_up_count": 0,
            "broken_count": 0,
        }

    limit_up = int(snapshot.get("limit_up_count") or 0)
    broken = int(snapshot.get("broken_count") or 0)
    total = limit_up + broken
    seal_rate = round(limit_up / total, 4) if total else None

    sectors = snapshot.get("sectors") or {}
    sector_total = sum(int(v.get("limit_up", 0) or 0) for v in sectors.values())
    concentration = None
    if sector_total > 0:
        top3 = sorted((int(v.get("limit_up", 0) or 0) for v in sectors.values()), reverse=True)[:3]
        concentration = round(sum(top3) / sector_total, 4)

    return {
        "seal_rate": seal_rate,
        "promotion_rate": promotion_rate,
        "max_height": snapshot.get("max_height"),
        "sector_concentration": concentration,
        "limit_up_count": limit_up,
        "broken_count": broken,
    }


def sentiment_state(metrics: dict) -> str:
    """判定市场情绪状态：ice（冰点）/ hot（亢奋）/ normal。

    Args:
        metrics: market_sentiment_metrics 的输出

    Returns:
        "ice" | "hot" | "normal"
    """
    seal_rate = metrics.get("seal_rate")
    promotion = metrics.get("promotion_rate")
    max_height = metrics.get("max_height") or 0
    concentration = metrics.get("sector_concentration")

    # 冰点：封板率低，或晋级率低（历史充足时）
    if (seal_rate is not None and seal_rate < SEAL_RATE_ICE) or (promotion is not None and promotion < PROMOTION_ICE):
        return "ice"

    # 亢奋：封板率高 + 连板高度高 + 资金拥挤（板块集中）
    if (
        seal_rate is not None
        and seal_rate > SEAL_RATE_HOT
        and max_height >= HOT_MAX_HEIGHT
        and (concentration is None or concentration >= HOT_SECTOR_CONCENTRATION)
    ):
        return "hot"

    return "normal"


def sentiment_overlay_multipliers(metrics: dict) -> dict:
    """市场级情绪 → 因子 multiplier 调整（overlay 第 5 层）。

    情绪冰点（封板率低/晋级率低）：压制 momentum（追高风险最大），
      提升 quality/valuation（防御属性）。
    情绪亢奋（封板率高 + 高度高 + 资金拥挤）：压制 momentum（避免在亢奋期追高）。

    Args:
        metrics: market_sentiment_metrics 的输出

    Returns:
        {factor: multiplier}；情绪正常时返回空 dict（不调整）
    """
    state = sentiment_state(metrics)
    if state == "ice":
        return {"momentum": 0.7, "quality": 1.1, "valuation": 1.1}
    if state == "hot":
        return {"momentum": 0.8}
    return {}


__all__ = [
    "SEAL_RATE_ICE",
    "SEAL_RATE_HOT",
    "PROMOTION_ICE",
    "HOT_MAX_HEIGHT",
    "HOT_SECTOR_CONCENTRATION",
    "market_sentiment_metrics",
    "sentiment_state",
    "sentiment_overlay_multipliers",
]
