"""
徐翔专属评分函数。

维度：基本面(5%) + 估值(5%) + 技术面(30%) + 情绪/题材(50%) + 风险(10%)
精确复现 experts/xu_xiang.md §九 评分矩阵中的阈值规则。
"""

from typing import Dict

from ._utils import _safe_float


def score(stock_data: dict) -> Dict[str, float]:
    """徐翔专属评分：涨停基因 + 板块联动封单 + 流通市值。"""
    quote = stock_data.get("quote") or {}
    fin = stock_data.get("finance") or {}
    market = stock_data.get("market_features") or {}
    kline_data = stock_data.get("kline_data") or {}

    # 基本面：仅排雷
    eps = _safe_float(fin.get("EPSJB") or fin.get("eps"))
    base = 60 if eps > 0 else 0

    # 估值：流通市值
    circ_cap = _safe_float(quote.get("circulating_cap"))
    if 30 <= circ_cap <= 150:
        val = 100
    elif 150 < circ_cap <= 300:
        val = 60
    elif circ_cap > 500 or circ_cap < 30:
        val = 0
    else:
        val = 50

    # 技术面：涨停板基因
    limit_up_30d = market.get("limit_up_30d_count", 0)
    if limit_up_30d is None or limit_up_30d == 0:
        # 从 K 线数据估算
        closes = kline_data.get("closes") or []
        if len(closes) >= 2:
            limit_up_30d = sum(
                1
                for i in range(1, len(closes))
                if closes[i - 1] > 0 and (closes[i] / closes[i - 1] - 1) >= 0.085
            )
    if limit_up_30d >= 2:
        tech = 100
    elif limit_up_30d >= 1:
        tech = 50
    else:
        tech = 0

    # 情绪/题材：板块联动 + 封单强度
    sector_limits = market.get("sector_limit_up_count", 0)
    seal_ratio = market.get("seal_to_circ_ratio", 0)
    if sector_limits >= 3 and seal_ratio > 0.01:
        sent = 100
    elif sector_limits >= 2:
        sent = 60
    elif sector_limits >= 1:
        sent = 20
    else:
        sent = 10

    # 风险：大盘趋势 + 炸板率 + 监管
    idx_above_ma20 = market.get("index_above_ma20", True)
    limit_up_total = market.get("limit_up_count", 0)
    if idx_above_ma20 and limit_up_total > 50:
        risk = 100
    elif not idx_above_ma20 or limit_up_total < 20:
        risk = 20
    else:
        risk = 60

    return {
        "基本面": base,
        "估值": val,
        "技术面": tech,
        "情绪/题材": sent,
        "风险": risk,
    }


def score_with_reasoning(stock_data: dict) -> Dict[str, object]:
    """徐翔评分（含推理链）。

    v2.2.0 起统一使用 generic_score_with_reasoning 模板。
    """
    from experts.registry import EXPERT_REGISTRY
    from ._utils import generic_score_with_reasoning

    profile = EXPERT_REGISTRY["xu_xiang"]
    return generic_score_with_reasoning(profile, score, stock_data)
