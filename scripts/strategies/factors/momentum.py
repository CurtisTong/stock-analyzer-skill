"""
动量因子评分：趋势、20日收益、量能比、MACD、RSI、量价配合。
"""
from common import to_float, clamp


def momentum_score(features: dict, quote: dict) -> float:
    """动量因子评分。满分 100。"""
    ret20 = features["ret20"]
    volume_ratio = features["volume_ratio"]
    turnover = to_float(quote.get("turnover"))

    # 趋势基础分：缩小上升/下降差距，避免过度敏感
    score = 40 if features["trend"] > 0 else 20 if features["trend"] == 0 else 12
    score += clamp((ret20 + 8) / 25 * 22)
    score += clamp((volume_ratio - 0.6) / 1.4 * 12)
    score += clamp(turnover / 6 * 6)

    # MACD 金叉加分，死叉扣分
    macd_signal = features.get("macd_signal", 0)
    if macd_signal > 0:
        score += 10
    elif macd_signal < 0:
        score -= 8

    # RSI 合理区间加分，过度区域扣分
    rsi = features.get("rsi", 50)
    if 30 <= rsi <= 70:
        score += 5
    elif rsi > 80:
        score -= 6
    elif rsi < 20:
        score -= 4

    # 量价配合加分
    vol_price_signal = features.get("vol_price_signal", 0)
    if vol_price_signal > 0:
        score += 8
    elif vol_price_signal < 0:
        score -= 10

    return clamp(score)
