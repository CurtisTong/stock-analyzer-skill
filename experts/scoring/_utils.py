"""
专家评分通用工具函数。

包含所有专家共用的基础工具：安全浮点转换、数值钳制、维度评分计算等。
"""

import threading
from typing import Dict, Optional

from .. import ExpertProfile

# ═══════════════════════════════════════════════════════════════
# 延迟导入辅助
# ═══════════════════════════════════════════════════════════════

_clamp_fn = None
_get_scoring_config_fn = None
_lock = threading.Lock()


def _get_clamp():
    """延迟导入 clamp，处理跨模块路径问题（DCL + threading.Lock 保护）。"""
    global _clamp_fn
    if _clamp_fn is not None:
        return _clamp_fn
    with _lock:
        if _clamp_fn is not None:
            return _clamp_fn
        try:
            from common.utils import clamp

            _clamp_fn = clamp
        except ImportError:

            def _clamp_fn(val, lo=0.0, hi=100.0):
                return max(lo, min(hi, val))

    return _clamp_fn


def _get_scoring_config():
    """延迟导入 get_scoring_config，处理跨模块路径问题（DCL + threading.Lock 保护）。"""
    global _get_scoring_config_fn
    if _get_scoring_config_fn is not None:
        return _get_scoring_config_fn
    with _lock:
        if _get_scoring_config_fn is not None:
            return _get_scoring_config_fn
        try:
            from config import get_scoring_config

            _get_scoring_config_fn = get_scoring_config
        except ImportError:

            def _get_scoring_config_fn(key=None, default=None):
                return default

    return _get_scoring_config_fn


# ═══════════════════════════════════════════════════════════════
# 维度名别名映射（I19）
# 不同专家可能用不同的维度名（如 momentum_trader 用"情绪/资金"而非标准"情绪"）
# ═══════════════════════════════════════════════════════════════

_DIM_ALIASES: Dict[str, str] = {
    "情绪/资金": "情绪",
    "资金/情绪": "情绪",
    "资金面": "资金",
    "估值/质量": "估值",
    "质量/估值": "质量",
    "技术/趋势": "技术",
    "趋势/技术": "技术",
}


def _normalize_dim_name(name: str) -> str:
    """将维度名别名映射到标准名称。"""
    return _DIM_ALIASES.get(name, name)


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
        # I19: 维度名别名映射--允许专家用"情绪/资金"等非标准名
        score = dim_scores.get(dim)
        if score is None:
            score = dim_scores.get(_normalize_dim_name(dim), 50.0)
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
    # 通用推理链模板（v2.2.0，所有专家共用）
    "generic_score_with_reasoning",
    "format_generic_reasoning",
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


def _score_valuation(quote: dict, fin: dict, industry: str = "默认") -> float:
    """估值维度：PE + PEG。PE 段使用统一的 pe_percentile 行业差异化估值。"""
    try:
        from strategies.factors.common import pe_percentile as _pe_percentile
    except ImportError:
        # strategies 模块不可用时，使用简单 PE 分位估算
        def _pe_percentile(pe, industry="默认"):
            if pe <= 0:
                return 50
            if pe <= 15:
                return 20
            if pe <= 25:
                return 40
            if pe <= 40:
                return 60
            return 80

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
        # _pe_percentile 返回 0-100（越高越贵），反转为价值分（越高越便宜）
        score += 100 - _pe_percentile(pe, industry)
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


# ═══════════════════════════════════════════════════════════════
# 通用推理链模板（v2.2.0，所有专家共用）
# 原 buffett.py 独有 score_with_reasoning + format_reasoning 模式
# 在 14 位专家间统一：每位专家只需把 score() 包装到 generic_score_with_reasoning
# ═══════════════════════════════════════════════════════════════


def _score_to_reason_label(score: float) -> str:
    """通用分值到语义标签的映射（v2.2.0 推理链统一）。

    将 0-100 维度分映射为带 emoji 的语义描述，用于 score_with_reasoning 输出。
    """
    if score >= 80:
        return "✅ 优秀"
    if score >= 60:
        return "✅ 良好"
    if score >= 40:
        return "⚠️ 中性"
    if score >= 20:
        return "⚠️ 较弱"
    return "❌ 较差"


def generic_score_with_reasoning(
    profile: "ExpertProfile",
    score_fn,
    stock_data: dict,
) -> Dict[str, object]:
    """通用 score_with_reasoning（v2.2.0）。

    把任一专家的 score() 包装成"含推理链"的版本，统一 buffett 的私有模式。
    原 buffett.py 的 score_with_reasoning 是手写 160 行；本通用模板让 13 位
    其他专家只需 1 行调用即可获得等价输出。

    Args:
        profile: 专家人设（含 5 维度权重 + display_name + group）
        score_fn: 专家的 score(stock_data) -> Dict[dim, 0-100]
        stock_data: 股票数据 dict

    Returns:
        {
            "scores": {dim: float, ...},
            "reasoning": [str, ...],
            "dimensions": {dim: {"score": float, "weight": float, "reason": str}, ...},
            "display_name": str,
            "expert_id": str,
        }
    """
    scores = score_fn(stock_data)
    reasoning = []
    dimensions = {}

    for dim, score in scores.items():
        weight = profile.weights.get(dim, 0.0) / 100.0
        label = _score_to_reason_label(score)
        reason = f"{label}：{dim}维度分 {score:.0f}/100（权重 {weight:.0%}）"
        reasoning.append(reason)
        dimensions[dim] = {
            "score": score,
            "weight": weight,
            "reason": reason,
        }

    return {
        "scores": scores,
        "reasoning": reasoning,
        "dimensions": dimensions,
        "display_name": getattr(profile, "display_name", profile.name),
        "expert_id": profile.name,
    }


def format_generic_reasoning(
    result: dict,
    total_score: Optional[float] = None,
) -> str:
    """通用推理链 markdown 输出（v2.2.0）。

    与 buffett.py 的 format_reasoning 等价但通用化。
    """
    reasoning = result["reasoning"]
    dimensions = result["dimensions"]
    name = result.get("display_name", result.get("expert_id", "专家"))

    if total_score is None:
        total = 0.0
        for dim, info in dimensions.items():
            total += info["score"] * info["weight"]
        total_score = total

    lines = [
        f"📊 {name}评分详情",
        "",
        f"总分：{total_score:.0f}/100",
        "",
        "## 评分明细",
        "",
        "| 维度 | 权重 | 得分 | 推理过程 |",
        "|------|------|------|----------|",
    ]

    for dim, info in dimensions.items():
        lines.append(
            f"| {dim} | {info['weight']:.0%} | {info['score']:.0f} | {info['reason']} |"
        )

    lines.append("")
    lines.append("## 关键判断")
    lines.append("")
    for r in reasoning:
        lines.append(f"- {r}")

    return "\n".join(lines)
