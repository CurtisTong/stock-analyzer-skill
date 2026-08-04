"""容量票识别（大市值+高成交额+趋势中的短线溢价标的）。

策略定义：带有短线溢价的趋势股，大市值容量，能容纳大资金，几百亿。
通常是机构趋势股，图形光滑，走势明显，按图施工（均线）。

依赖: technical.moving_average (ma_system)
"""

from common import to_float
from technical.moving_average import ma_system

# 默认阈值（可被 limits.yaml 覆盖）
_DEFAULT_MIN_CAP = 300  # 最小总市值（亿）
_DEFAULT_MIN_AMOUNT = 10  # 最小日成交额（亿）
_DEFAULT_SCORE_THRESHOLD = 70
_AMOUNT_YI = 1e8  # 元 -> 亿


def detect_capacity_stock(quote, closes, highs=None, lows=None):
    """识别容量票（四维打分 0-100）。

    Args:
        quote: 行情快照 dict（含 total_cap 亿, amount 元）
        closes: 收盘价序列 list[float]
        highs/lows: 最高/最低价序列（预留，当前未使用）

    Returns:
        dict: {
            "is_capacity": bool,
            "score": int,          # 0-100
            "reasons": list[str],
            "cap": float,          # 总市值（亿）
            "amount_yi": float,    # 日成交额（亿）
            "trend": str,          # 趋势状态
        }
    """
    # 加载配置阈值
    try:
        from config.loader import ConfigLoader

        min_cap = ConfigLoader.get(
            "limits.yaml", "capacity_stock.min_cap", _DEFAULT_MIN_CAP
        )
        min_amount = ConfigLoader.get(
            "limits.yaml", "capacity_stock.min_amount", _DEFAULT_MIN_AMOUNT
        )
        score_threshold = ConfigLoader.get(
            "limits.yaml", "capacity_stock.score_threshold", _DEFAULT_SCORE_THRESHOLD
        )
    except Exception:
        min_cap = _DEFAULT_MIN_CAP
        min_amount = _DEFAULT_MIN_AMOUNT
        score_threshold = _DEFAULT_SCORE_THRESHOLD

    total_cap = to_float(quote.get("total_cap", 0)) if quote else 0
    amount_yuan = to_float(quote.get("amount", 0)) if quote else 0
    amount_yi = amount_yuan / _AMOUNT_YI

    reasons = []
    score = 0

    # ── 维度1：市值（30分）──
    if total_cap >= min_cap:
        score += 30
        reasons.append(f"总市值{total_cap:.0f}亿(大市值容量)")
    elif total_cap >= min_cap * 0.67:  # 200亿（300的2/3）
        score += 20
        reasons.append(f"总市值{total_cap:.0f}亿(中等容量)")

    # ── 维度2：成交额（30分）──
    if amount_yi >= min_amount:
        score += 30
        reasons.append(f"日成交额{amount_yi:.1f}亿(高流动性)")
    elif amount_yi >= min_amount * 0.5:  # 5亿
        score += 20
        reasons.append(f"日成交额{amount_yi:.1f}亿(中等流动性)")

    # ── 维度3：趋势（25分）──
    # 直接用 MA5/MA10/MA20 判断趋势（不依赖 ma_system 的 alignment，
    # 后者需 4 条以上均线有值才判定，对 30 根日K过于严格）
    trend = "数据不足"
    if closes and len(closes) >= 20:
        ma = ma_system(closes)
        ma5 = ma.get("ma5")
        ma10 = ma.get("ma10")
        ma20 = ma.get("ma20")
        if ma5 and ma10 and ma20:
            if ma5 > ma10 > ma20:
                score += 25
                trend = "多头排列(趋势中)"
                reasons.append("均线多头排列(趋势确认)")
            elif ma5 < ma10 < ma20:
                trend = "空头排列"
            else:
                score += 15
                trend = "交叉震荡"
        elif ma5 and ma20:
            if ma5 > ma20:
                score += 20
                trend = "MA5>MA20(偏多)"
            else:
                trend = "MA5<MA20(偏空)"

    # ── 维度4：短线溢价（15分）──
    if closes and len(closes) >= 25:
        ma = ma_system(closes)
        ma5 = ma.get("ma5")
        ma20 = ma.get("ma20")
        recent_gain = (closes[-1] - closes[-5]) / max(closes[-5], 0.01) * 100
        if ma5 and ma20 and ma5 > ma20 and recent_gain > 0:
            score += 15
            reasons.append(f"MA5>MA20+近5日涨{recent_gain:.1f}%(短线溢价)")

    is_capacity = score >= score_threshold

    return {
        "is_capacity": is_capacity,
        "score": score,
        "reasons": reasons,
        "cap": round(total_cap, 1),
        "amount_yi": round(amount_yi, 2),
        "trend": trend,
    }
