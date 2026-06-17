"""
动量因子评分：趋势、20日收益、量能比、MACD、RSI、量价配合。
MACD 和 RSI 均为趋势确认指标，同向时降权以避免信息冗余。

2026 更新：支持市场环境动态衰减——量化高活跃期降低动量权重。
"""

from common import to_float, clamp

# 市场环境对动量因子的衰减系数
_MOMENTUM_DECAY_TABLE = {
    "quant_high": 0.70,  # 量化高活跃：趋势持续时间缩短，假突破增多
    "quant_normal": 0.90,  # 量化正常
    "quant_low": 1.00,  # 量化低活跃：趋势持续性恢复
}


def _detect_quant_activity(quote: dict, features: dict) -> str:
    """检测量化活跃度。只使用全市场成交额，无数据时返回默认。"""
    market_amount = to_float(quote.get("market_amount", 0))
    if market_amount > 12000:
        return "quant_high"
    if market_amount > 8000:
        return "quant_normal"
    return "quant_normal"


def momentum_score(features: dict, quote: dict) -> float:
    """动量因子评分。满分 100。

    2026 更新：根据市场量化活跃度动态衰减动量权重。
    量化高活跃环境 → 趋势跟踪信号可靠性下降，衰减至 0.7。
    """
    ret20 = features["ret20"]
    volume_ratio = features["volume_ratio"]
    turnover = to_float(quote.get("turnover"))

    # 检测量化活跃度并应用衰减
    quant_regime = _detect_quant_activity(quote, features)
    decay = _MOMENTUM_DECAY_TABLE.get(quant_regime, 1.0)

    # 估值衰减：高估值股票的动量信号可靠性低（泡沫而非趋势）
    pe = to_float(quote.get("pe"))
    if pe > 0:
        # 优先用已有的 pe_percentile，否则从行业阈值估算
        pe_pct = to_float(quote.get("pe_percentile", 0))
        if pe_pct <= 0:
            try:
                from strategies.thresholds import get_industry_threshold
                from classifier import infer_industry

                industry = infer_industry(quote.get("name", ""), quote.get("code", ""))
                pe_low = get_industry_threshold(industry, "pe_undervalued", 15)
                pe_mid = get_industry_threshold(industry, "pe_reasonable", 25)
                pe_high = get_industry_threshold(industry, "pe_expensive", 40)
            except Exception:
                pe_low, pe_mid, pe_high = 15, 25, 40
            if pe <= pe_low:
                pe_pct = 15
            elif pe <= pe_mid:
                pe_pct = 15 + (pe - pe_low) / (pe_mid - pe_low) * 35
            elif pe <= pe_high:
                pe_pct = 50 + (pe - pe_mid) / (pe_high - pe_mid) * 30
            else:
                pe_pct = min(95, 80 + (pe - pe_high) / pe_high * 20)
        if pe_pct > 80:
            decay *= 0.45  # 估值极高位，动量信号大幅降权
        elif pe_pct > 65:
            decay *= 0.70  # 估值偏高，适度降权

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
    # 与 MACD 同向时降权（避免趋势类信息重复计算）
    rsi = features.get("rsi", 50)
    rsi_weight = (
        0.6 if (macd_signal > 0 and rsi > 50) or (macd_signal < 0 and rsi < 50) else 1.0
    )
    if 30 <= rsi <= 70:
        score += int(5 * rsi_weight)
    elif rsi > 80:
        score -= int(6 * rsi_weight)
    elif rsi < 20:
        score -= int(4 * rsi_weight)

    vol_price_signal = features.get("vol_price_signal", 0)
    if vol_price_signal > 0:
        score += 8
    elif vol_price_signal < 0:
        score -= 10

    # 量化衰减：趋势信号部分按regime打折，量价信号全额保留
    # 量在量化环境中更可靠（成交量反映真实资金动向）
    trend_part = score
    vol_price_part = 8 if vol_price_signal > 0 else (-10 if vol_price_signal < 0 else 0)

    final_score = (trend_part - vol_price_part) * decay + vol_price_part
    return clamp(final_score)
