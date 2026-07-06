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
    """检测量化活跃度。review#6 修复：阈值改用动态百分位而非硬编码 12000。

    优先级：
      1. quote["market_amount_p75"] — 调用方提供的 75% 分位（推荐）
      2. quote["market_amount"] > 12000 — 硬编码 fallback（保守）
    """
    market_amount = to_float(quote.get("market_amount", 0))
    p75 = to_float(quote.get("market_amount_p75", 0))
    if p75 > 0 and market_amount > p75:
        return "quant_high"
    if p75 <= 0 and market_amount > 12000:  # 兼容旧调用
        return "quant_high"
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

    # 估值衰减：用统一的 pe_percentile
    pe = to_float(quote.get("pe"))
    if pe > 0:
        pe_pct = to_float(quote.get("pe_percentile", 0))
        if pe_pct <= 0:
            from strategies.factors.common import pe_percentile

            industry = quote.get("industry", "默认")
            pe_pct = pe_percentile(pe, industry)
        if pe_pct > 80:
            decay *= 0.45
        elif pe_pct > 65:
            decay *= 0.70

    # 趋势基础分：review#7 收敛（40→30, 20→18, 12→15），为量价确认信号腾出空间
    score = 30 if features["trend"] > 0 else 18 if features["trend"] == 0 else 15
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
        score += round(5 * rsi_weight, 2)
    elif rsi > 80:
        score -= round(6 * rsi_weight, 2)
    elif rsi < 20:
        score -= round(4 * rsi_weight, 2)

    vol_price_signal = features.get("vol_price_signal", 0)
    if vol_price_signal > 0:
        score += 8
    elif vol_price_signal < 0:
        score -= 10

    # 量化衰减：除量价信号外的所有信号按 regime 打折，量价信号全额保留
    # 量在量化环境中更可靠（成交量反映真实资金动向）
    # 注意：base_score 包含趋势+收益+量比+换手+MACD+RSI 所有信号，
    # vol_price_part 已在上方加/减到 base_score 中，此处先减出再衰减后加回
    base_score = score
    vol_price_part = 8 if vol_price_signal > 0 else (-10 if vol_price_signal < 0 else 0)

    final_score = (base_score - vol_price_part) * decay + vol_price_part
    return clamp(final_score)
