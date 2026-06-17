"""
赵老哥专属评分函数。

维度：基本面(10%) + 估值(8%) + 技术面(35%) + 情绪/题材(35%) + 风险(12%)
精确复现 experts/zhao_laoge.md §九 评分矩阵中的阈值规则。
"""
import statistics
from typing import Dict

from ._utils import _safe_float


def score(stock_data: dict) -> Dict[str, float]:
    """赵老哥专属评分：均线排列 + 题材生命周期 + 流通市值。"""
    quote = stock_data.get("quote") or {}
    kline = stock_data.get("kline_features") or {}
    kline_data = stock_data.get("kline_data") or {}
    market = stock_data.get("market_features") or {}

    # 基本面：题材容量（简化）
    base = 50

    # 估值：流通市值
    circ_cap = _safe_float(quote.get("circulating_cap"))
    if 50 <= circ_cap <= 300:
        val = 100
    elif 30 <= circ_cap <= 500:
        val = 60
    elif circ_cap > 1000:
        val = 20
    else:
        val = 50

    # 技术面：均线系统
    closes = kline_data.get("closes") or []
    if len(closes) >= 20:
        ma5 = statistics.mean(closes[-5:])
        ma10 = statistics.mean(closes[-10:])
        ma20 = statistics.mean(closes[-20:])
        if ma5 > ma10 > ma20:
            tech = 100
        elif ma5 < ma10 < ma20:
            tech = 0
        else:
            tech = 70
    else:
        trend = kline.get("trend", 0)
        tech = 80 if trend > 0 else (40 if trend == 0 else 10)

    # 情绪/题材：量价配合
    volumes = kline_data.get("volumes") or []
    if len(closes) >= 10 and len(volumes) >= 10:
        recent_vol = statistics.mean(volumes[-5:])
        prev_vol = statistics.mean(volumes[-10:-5])
        if recent_vol > prev_vol * 1.2 and closes[-1] > statistics.mean(closes[-5:-1]):
            sent = 100
        elif recent_vol < prev_vol * 0.8:
            sent = 60
        else:
            sent = 40
    else:
        sent = 50

    # 风险：龙头地位 + 20日均线（渐进式扣分，龙头低吸风格破20日线常是买点）
    if len(closes) >= 20:
        ma20 = statistics.mean(closes[-20:])
        if ma20 > 0:
            pullback_pct = (closes[-1] - ma20) / ma20 * 100
            if pullback_pct >= 0:
                risk = 80
            elif pullback_pct >= -3:
                risk = 60
            elif pullback_pct >= -8:
                risk = 30
            else:
                risk = 10
        else:
            risk = 50
    else:
        risk = 60

    return {"基本面": base, "估值": val, "技术面": tech, "情绪/题材": sent, "风险": risk}


def score_with_reasoning(stock_data: dict) -> Dict[str, object]:
    """赵老哥评分（含推理链）。

    v2.2.0 起统一使用 generic_score_with_reasoning 模板。
    """
    from experts.registry import EXPERT_REGISTRY
    from ._utils import generic_score_with_reasoning
    profile = EXPERT_REGISTRY["zhao_laoge"]
    return generic_score_with_reasoning(profile, score, stock_data)
