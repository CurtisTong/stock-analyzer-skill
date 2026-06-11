"""
专家评分骨架。

v1.3.2 引入：根据 expert 人设的维度权重和给定的维度分（0-100），
计算加权总分。完整真实评分仍由 Claude Code 在 debate 模式中
读 experts/*.md 给出；本模块提供：

- score_from_dimensions(profile, dim_scores) -> float: 按权重加总
- score_expert(profile, stock_data) -> float: 用内置启发式计算维度分

Args:
    profile: ExpertProfile 实例
    dim_scores: Dict[dimension_name, 0..100]，缺维度视为 50 (中性)

Returns:
    0-100 之间的浮点分
"""
from typing import Dict
from . import ExpertProfile, direction_from_score


def score_from_dimensions(profile: ExpertProfile, dim_scores: Dict[str, float]) -> float:
    """根据维度分和权重计算专家总分（0-100）。

    Args:
        profile: 专家人设（含 5 维度权重）
        dim_scores: 维度分 dict。缺维度视为 50（中性）。

    Returns:
        0-100 之间的总分
    """
    total = 0.0
    for dim, weight in profile.weights.items():
        score = dim_scores.get(dim, 50.0)
        # 钳制到 0-100
        score = max(0.0, min(100.0, float(score)))
        total += score * (weight / 100.0)
    return max(0.0, min(100.0, total))


def dimension_breakdown(profile: ExpertProfile, dim_scores: Dict[str, float]) -> Dict[str, float]:
    """返回每个维度的加权贡献（用于在 debate 报告中显示）。

    与 score_from_dimensions 一致，对输入分值做 0-100 钳制。
    """
    breakdown = {}
    for dim, weight in profile.weights.items():
        score = dim_scores.get(dim, 50.0)
        score = max(0.0, min(100.0, float(score)))
        breakdown[dim] = round(score * (weight / 100.0), 2)
    return breakdown


# ═══════════════════════════════════════════════════════════════
# 内置启发式：基于 stock_data 给维度打 0-100 分
# ═══════════════════════════════════════════════════════════════

def _score_fundamentals(fin: dict) -> float:
    """基本面维度：ROE + 净利增速 + 营收增速 + 毛利率。"""
    if not fin:
        return 50.0
    roe = float(fin.get("roe") or fin.get("ROEJQ") or 0)
    profit_yoy = float(fin.get("net_profit_yoy") or fin.get("PARENTNETPROFITTZ") or 0)
    revenue_yoy = float(fin.get("revenue_yoy") or fin.get("TOTALOPERATEREVETZ") or 0)
    gross_margin = float(fin.get("gross_margin") or fin.get("XSMLL") or 0)
    debt = float(fin.get("debt_ratio") or fin.get("ZCFZL") or 0)

    # 5 项均分：ROE / 净利增速 / 营收增速 / 毛利率 / 负债率 各贡献 0-20，
    # 合计 0-100 后总分 = sum / 5。
    score = 0
    score += min(100, roe * 5)  # ROE 20% → 100
    score += min(100, max(0, profit_yoy + 50))  # -50 → 0, +50 → 100
    score += min(100, max(0, revenue_yoy + 50))  # -50 → 0, +50 → 100
    score += min(100, gross_margin * 2)  # 50% → 100
    score += min(100, max(0, 100 - debt))  # 负债率越低越好
    return round(score / 5, 1)


def _score_valuation(quote: dict, fin: dict) -> float:
    """估值维度：PE + PEG。"""
    if not quote:
        return 50.0
    pe = float(quote.get("pe") or 0)
    pb = float(quote.get("pb") or 0)
    growth = float(fin.get("net_profit_yoy") or fin.get("PARENTNETPROFITTZ") or 0) if fin else 0

    # PE/PB 都缺失（含亏损股 PE<0 被置 0）→ 无法估值，返回中性
    if pe <= 0 and pb <= 0:
        return 50.0

    score = 0
    if pe > 0:
        if pe <= 15:
            score += 60
        elif pe <= 25:
            score += 45
        elif pe <= 40:
            score += 25
        else:
            score += 10
    if pb > 0 and pb <= 2:
        score += 20
    elif pb > 0 and pb <= 5:
        score += 10
    # PEG bonus
    if pe > 0 and growth > 0:
        peg = pe / growth
        if peg <= 1.0:
            score += 20
        elif peg <= 2.0:
            score += 10
    return min(100, max(0, score))


def _score_technical(kline_features: dict) -> float:
    """技术面维度：趋势 + RSI + MACD。"""
    if not kline_features:
        return 50.0
    score = 50  # 中性
    trend = kline_features.get("trend", 0)
    if trend > 0:
        score += 20
    elif trend < 0:
        score -= 20

    rsi = kline_features.get("rsi", 50)
    if 30 <= rsi <= 70:
        score += 5
    elif rsi > 80:
        score -= 15
    elif rsi < 20:
        score -= 5  # 超卖可考虑反弹

    macd = kline_features.get("macd_signal", 0)
    if macd > 0:
        score += 10
    elif macd < 0:
        score -= 10

    return max(0, min(100, score))


def _score_sentiment(market_features: dict) -> float:
    """情绪/题材维度：基于市场行情（涨停家数/炸板率/板块强度）。"""
    if not market_features:
        return 50.0
    score = 50
    limit_up_count = market_features.get("limit_up_count", 0)
    if limit_up_count > 80:
        score += 25
    elif limit_up_count > 40:
        score += 10
    elif limit_up_count < 20:
        score -= 20

    limit_down_count = market_features.get("limit_down_count", 0)
    if limit_down_count > 50:
        score -= 30
    elif limit_down_count > 20:
        score -= 15

    return max(0, min(100, score))


def score_expert(
    profile: ExpertProfile,
    stock_data: dict,
) -> dict:
    """根据内置启发式为一位专家打分。

    Args:
        profile: 专家人设
        stock_data: 包含 quote/finance/kline_features/market_features 字段

    Returns:
        {
            "score": 0-100 总分,
            "direction": 方向标签,
            "breakdown": {dim: weighted_contribution, ...}
        }
    """
    quote = stock_data.get("quote") or {}
    fin = stock_data.get("finance") or {}
    kline_features = stock_data.get("kline_features") or {}
    market_features = stock_data.get("market_features") or {}

    # 维度分（按专家的 5 维度命名）
    dim_scores: Dict[str, float] = {}
    for dim in profile.weights:
        if dim in ("基本面", "fundamentals"):
            dim_scores[dim] = _score_fundamentals(fin)
        elif dim in ("估值", "valuation"):
            dim_scores[dim] = _score_valuation(quote, fin)
        elif dim in ("技术面", "technical"):
            dim_scores[dim] = _score_technical(kline_features)
        elif dim in ("情绪", "情绪/题材", "情绪/反身性", "sentiment"):
            dim_scores[dim] = _score_sentiment(market_features)
        elif dim in ("安全边际", "margin_of_safety", "margin"):
            # 安全边际 ≈ 低估值 + 低负债 + 强护城河（用 ROE 代理）
            margin = (_score_valuation(quote, fin) * 0.5 +
                      _score_fundamentals(fin) * 0.5)
            dim_scores[dim] = round(margin, 1)
        elif dim in ("风险", "risk"):
            # 风险维度：高分 = 风险可控（好）。
            # 综合基本面稳健度 + 估值安全性 + 负债率。
            risk = (
                _score_fundamentals(fin) * 0.4 +
                _score_valuation(quote, fin) * 0.3 +
                (100 - float(fin.get("debt_ratio") or fin.get("ZCFZL") or 50)) * 0.3
            )
            dim_scores[dim] = round(max(0, min(100, risk)), 1)
        else:
            dim_scores[dim] = 50.0

    total = score_from_dimensions(profile, dim_scores)
    return {
        "score": round(total, 1),
        "direction": direction_from_score(total),
        "breakdown": dimension_breakdown(profile, dim_scores),
        "dim_scores": dim_scores,
    }


__all__ = [
    "score_from_dimensions",
    "dimension_breakdown",
    "score_expert",
]
