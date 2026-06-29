"""
作手新一专属评分函数。

维度：基本面(8%) + 估值(5%) + 技术面(40%) + 情绪(35%) + 风险(12%)
精确复现 experts/zuoshou_xinyi.md §九 评分矩阵中的阈值规则。
"""

import statistics
from typing import Dict

from ._utils import _safe_float, _get_clamp


def score(stock_data: dict) -> Dict[str, float]:
    """作手新一专属评分：缩量回调 + K线反转形态 + 强势股基因。"""
    quote = stock_data.get("quote") or {}
    fin = stock_data.get("finance") or {}
    market = stock_data.get("market_features") or {}
    kline_data = stock_data.get("kline_data") or {}

    # 基本面：强势股基因
    limit_up_30d = market.get("limit_up_30d_count", 0)
    if limit_up_30d >= 4:
        base = 100
    elif limit_up_30d >= 1:
        base = 60
    else:
        base = 0

    # 估值：流通市值 + 回调深度
    circ_cap = _safe_float(quote.get("circulating_cap"))
    pullback = _safe_float(market.get("pullback_pct"), -1)
    if 30 <= circ_cap <= 200:
        val = 100
    elif 10 <= circ_cap <= 300:
        val = 50
    else:
        val = 0
    if pullback > 62:
        val = _get_clamp()(val * 0.3)

    # 技术面：K线反转形态 + 缩量程度
    closes = kline_data.get("closes") or []
    volumes = kline_data.get("volumes") or []
    if len(closes) >= 10 and len(volumes) >= 10:
        peak_vol = max(volumes[-10:]) if volumes else 1
        recent_vol = statistics.mean(volumes[-3:]) if len(volumes) >= 3 else 1
        vol_ratio = recent_vol / peak_vol if peak_vol > 0 else 1

        last3 = closes[-3:]
        # 锤子线：下跌后下影线长、实体小、收在高点附近（简化：收阳且高于前低）
        is_hammer = len(last3) == 3 and last3[-2] < last3[-3] and last3[-1] > last3[-2]
        # 吞没形态：阳包阴（收阳且实体覆盖前一根阴线）
        is_engulfing = (
            len(last3) == 3
            and last3[-1] > last3[-2]
            and last3[-2] < last3[-3]
            and last3[-1] > last3[-3]
        )

        if vol_ratio <= 0.5 and (is_hammer or is_engulfing):
            tech = 100
        elif vol_ratio <= 0.5:
            tech = 60
        else:
            tech = 20
    else:
        tech = 40

    # 情绪：调整阶段
    if len(closes) >= 10:
        peak_idx = closes.index(max(closes))
        adjust_days = len(closes) - peak_idx - 1
        if 3 <= adjust_days <= 7:
            sent = 100
        elif adjust_days < 3:
            sent = 40
        else:
            sent = 30
    else:
        sent = 50

    # 风险：止损距离
    support = _safe_float(market.get("support_price"))
    price = _safe_float(quote.get("price"))
    if support > 0 and price > 0:
        stop_loss_pct = (price - support) / price * 100
        if stop_loss_pct < 3:
            risk = 100
        elif stop_loss_pct < 8:
            risk = 60
        else:
            risk = 20
    else:
        risk = 60

    return {"基本面": base, "估值": val, "技术面": tech, "情绪": sent, "风险": risk}


def score_with_reasoning(stock_data: dict) -> Dict[str, object]:
    """作手新一评分（含推理链）。

    v2.2.0 起统一使用 generic_score_with_reasoning 模板。
    """
    from experts.registry import EXPERT_REGISTRY
    from ._utils import generic_score_with_reasoning

    profile = EXPERT_REGISTRY["zuoshou_xinyi"]
    return generic_score_with_reasoning(profile, score, stock_data)
