"""
专家评分通用工具函数。

包含所有专家共用的基础工具：安全浮点转换、数值钳制、维度评分计算等。
"""

from typing import Dict

from .. import ExpertProfile

# ═══════════════════════════════════════════════════════════════
# 延迟导入辅助
# ═══════════════════════════════════════════════════════════════

_clamp_fn = None
_get_scoring_config_fn = None


def _get_clamp():
    """延迟导入 clamp，处理跨模块路径问题（缓存避免重复 import 查找）。"""
    global _clamp_fn
    if _clamp_fn is not None:
        return _clamp_fn
    try:
        from common.utils import clamp

        _clamp_fn = clamp
    except ImportError:
        _clamp_fn = lambda val, lo=0.0, hi=100.0: max(lo, min(hi, val))
    return _clamp_fn


def _get_scoring_config():
    """延迟导入 get_scoring_config，处理跨模块路径问题。"""
    global _get_scoring_config_fn
    if _get_scoring_config_fn is not None:
        return _get_scoring_config_fn
    try:
        from config import get_scoring_config

        _get_scoring_config_fn = get_scoring_config
    except ImportError:
        _get_scoring_config_fn = lambda key=None, default=None: default
    return _get_scoring_config_fn


# ═══════════════════════════════════════════════════════════════
# 基础工具函数
# ═══════════════════════════════════════════════════════════════


def _safe_float(val, default: float = 0.0) -> float:
    """安全转换为浮点数，失败返回默认值。"""
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def score_from_dimensions(
    profile: ExpertProfile, dim_scores: Dict[str, float]
) -> float:
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
        score = max(0.0, min(100.0, float(score)))
        total += score * (weight / 100.0)
    return max(0.0, min(100.0, total))


def dimension_breakdown(
    profile: ExpertProfile, dim_scores: Dict[str, float]
) -> Dict[str, float]:
    """返回每个维度的加权贡献（用于在 debate 报告中显示）。

    与 score_from_dimensions 一致，对输入分值做 0-100 钳制。
    """
    breakdown = {}
    for dim, weight in profile.weights.items():
        score = dim_scores.get(dim, 50.0)
        score = max(0.0, min(100.0, float(score)))
        breakdown[dim] = round(score * (weight / 100.0), 2)
    return breakdown


__all__ = [
    "_safe_float",
    "_get_clamp",
    "_get_scoring_config",
    "score_from_dimensions",
    "dimension_breakdown",
    # 通用启发式评分（v1.3.2，所有专家共用，作为 fallback）
    "_score_fundamentals",
    "_score_valuation",
    "_score_technical",
    "_score_sentiment",
]


# ═══════════════════════════════════════════════════════════════
# 通用启发式评分（v1.3.2，所有专家共用，作为 fallback）
# 供 sector_specialist / institution / risk_manager 等复用
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

    score = 0
    score += min(100, roe * 5)
    score += min(100, max(0, profit_yoy + 50))
    score += min(100, max(0, revenue_yoy + 50))
    score += min(100, gross_margin * 2)
    score += min(100, max(0, 100 - debt))
    return round(score / 5, 1)


def _score_valuation(quote: dict, fin: dict) -> float:
    """估值维度：PE + PEG。"""
    if not quote:
        return 50.0
    pe = float(quote.get("pe") or 0)
    pb = float(quote.get("pb") or 0)
    growth = (
        float(fin.get("net_profit_yoy") or fin.get("PARENTNETPROFITTZ") or 0)
        if fin
        else 0
    )

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
    score = 50
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
        score -= 5

    macd = kline_features.get("macd_signal", 0)
    if macd > 0:
        score += 10
    elif macd < 0:
        score -= 10

    return max(0, min(100, score))


def _score_sentiment(market_features: dict) -> float:
    """情绪/题材维度：基于市场行情（上涨家数比+涨停家数+炸板率+两融余额占比）。"""
    if not market_features:
        return 50.0
    score = 50

    advance_ratio = market_features.get("advance_ratio", None)
    if advance_ratio is not None:
        if advance_ratio > 0.6:
            score += 15
        elif advance_ratio > 0.4:
            score += 5
        elif advance_ratio < 0.3:
            score -= 15
        elif advance_ratio < 0.2:
            score -= 25

    nh_nl_ratio = market_features.get("nh_nl_ratio", None)
    if nh_nl_ratio is not None:
        if nh_nl_ratio > 1.5:
            score += 10
        elif nh_nl_ratio < 0.5:
            score -= 10
        elif nh_nl_ratio < 0.2:
            score -= 20

    limit_up_count = market_features.get("limit_up_count", 0)
    if limit_up_count > 80:
        score += 15
    elif limit_up_count > 50:
        score += 10
    elif limit_up_count > 30:
        score += 5
    elif limit_up_count < 15:
        score -= 15

    limit_down_count = market_features.get("limit_down_count", 0)
    if limit_down_count > 50:
        score -= 25
    elif limit_down_count > 20:
        score -= 10

    margin_ratio = market_features.get("margin_ratio", None)
    if margin_ratio is not None:
        if margin_ratio > 0.10:
            score -= 15
        elif margin_ratio < 0.04:
            score -= 5

    return max(0, min(100, score))
