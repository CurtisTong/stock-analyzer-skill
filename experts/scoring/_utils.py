"""
专家评分通用工具函数。

包含所有专家共用的基础工具：安全浮点转换、数值钳制、维度评分计算等。
"""

import threading
from typing import Dict, Optional

from ..types import ExpertProfile, DIMENSION_ALIASES as _DIM_ALIASES, normalize_dim, normalize_dim_scores

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
# 维度名别名归一化（C1 / ）
# 规范定义在 experts/types.py 的 DIMENSION_ALIASES / normalize_dim，
# 本模块导入复用，避免双数据源。不同专家可能用非标准维度名（如
# momentum_trader 用"情绪/资金"、soros 用"情绪/反身性"、topic_leader 用
# "情绪/题材"），score_from_dimensions / weighted_merge 入口归一到标准 5 维度。
# ═══════════════════════════════════════════════════════════════

# 向后兼容别名：_normalize_dim_name -> normalize_dim（规范名）
_normalize_dim_name = normalize_dim


# ═══════════════════════════════════════════════════════════════
# 基础工具函数
# ═══════════════════════════════════════════════════════════════


def _safe_float(val, default: float = 0.0) -> float:
    """安全转换为浮点数，失败返回默认值。"""
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def score_from_dimensions(profile: ExpertProfile, dim_scores: Dict[str, float]) -> float:
    """根据维度分和权重计算专家总分（0-100）。

    Args:
        profile: 专家人设（含 5 维度权重）
        dim_scores: 维度分 dict。缺维度视为 50（中性）。

    Returns:
        0-100 之间的总分
    """
    # 归一化维度分一侧：score() 返回的别名键（"情绪/反身性"等）归一到标准名，
    # 使其能与 profile.weights 的标准键对上（权重键加载时已归一化）。
    normalized = normalize_dim_scores(dim_scores)
    total = 0.0
    for dim, weight in profile.weights.items():
        # 权重键可能仍是别名（手动构造 ExpertProfile 而非 yaml_loader 加载），
        # 此时二次归一化兜底。
        score = normalized.get(dim)
        if score is None:
            score = normalized.get(_normalize_dim_name(dim), 50.0)
        score = max(0.0, min(100.0, float(score)))
        total += score * (weight / 100.0)
    return max(0.0, min(100.0, total))


def dimension_breakdown(profile: ExpertProfile, dim_scores: Dict[str, float]) -> Dict[str, float]:
    """返回每个维度的加权贡献（用于在 debate 报告中显示）。

    与 score_from_dimensions 一致，对输入分值做 0-100 钳制。
    """
    normalized = normalize_dim_scores(dim_scores)
    breakdown = {}
    for dim, weight in profile.weights.items():
        score = normalized.get(dim)
        if score is None:
            score = normalized.get(_normalize_dim_name(dim), 50.0)
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


# 金融业（银行/保险/券商/信托等）的负债率天然极高——银行负债率 92% 是
# 监管资本约束下的常态，不是财务风险信号。通用阈值（<30% 充裕 / ≥50%
# 不足）会把所有银行判成"安全边际不足"，与专家档案里明写的
# "ROE < 10% 或负债率 > 70%（**金融业除外**）"直接矛盾。
#
# （v1.26.0）此处提供统一豁免：金融业改用"资产质量 + 资本充足"视角的
# 宽松阈值，避免行业特性被当成公司缺陷。
_FINANCIAL_INDUSTRIES = ("银行", "保险", "证券", "券商", "信托", "金融", "资管", "期货")

# 金融业的负债率阈值（远高于通用阈值——只看是否极端）


def is_financial_industry(stock_data: dict) -> bool:
    """判断标的是否属于金融业（银行/保险/券商等）。

    优先取 stock_data["industry"]（experts_cli 由 classifier.infer_industry
    推断），其次看公司名关键词。
    """
    if not isinstance(stock_data, dict):
        return False
    industry = str(stock_data.get("industry") or "")
    if industry and any(key in industry for key in _FINANCIAL_INDUSTRIES):
        return True
    name = str((stock_data.get("quote") or {}).get("name") or "")
    return any(key in name for key in _FINANCIAL_INDUSTRIES)


def debt_ratio_score(debt: float, financial: bool = False) -> float:
    """按行业特性给负债率打分（0-100）。

    通用行业：<30% 充裕(100) / <50% 一般(60) / ≥50% 不足(0)
    金融业：≤92% 视为正常(100) / ≤95% 一般(60) / >95% 不足(0)
    """
    if financial:
        if debt <= 92.0:
            return 100.0
        if debt <= 95.0:
            return 60.0
        return 0.0
    if debt < 30:
        return 100.0
    if debt < 50:
        return 60.0
    return 0.0


def _score_fundamentals(fin: dict) -> float:
    """基本面维度：ROE + 净利增速 + 营收增速 + 毛利率。"""
    if not fin:
        return 50.0
    roe = float(fin.get("roe") or fin.get("ROEJQ") or 0)
    profit_yoy = float(fin.get("net_profit_yoy") or fin.get("PARENTNETPROFITTZ") or 0)
    revenue_yoy = float(fin.get("revenue_yoy") or fin.get("TOTALOPERATEREVETZ") or 0)
    gross_margin = float(fin.get("gross_margin") or fin.get("XSMLL") or 0)
    debt = float(fin.get("debt_ratio") or fin.get("ZCFZL") or 0)

    score = 0.0
    score += min(100, roe * 5)
    score += min(100, max(0, profit_yoy + 50))
    score += min(100, max(0, revenue_yoy + 50))
    score += min(100, gross_margin * 2)
    score += min(100, max(0, 100 - debt))
    return round(score / 5, 1)


def _score_valuation(quote: dict, fin: dict, industry: str = "默认") -> float:
    """估值维度：PE + PEG。PE 段使用统一的 pe_percentile 行业差异化估值。"""

    def _fallback_pe_percentile(pe: float, industry: str = "默认") -> float:
        """strategies 模块不可用时的简化 PE 分位估算。"""
        if pe <= 0:
            return 50.0
        if pe <= 15:
            return 20.0
        if pe <= 25:
            return 40.0
        if pe <= 40:
            return 60.0
        return 80.0

    pe_percentile_fn = _fallback_pe_percentile
    try:
        # （v1.26.0）修正导入路径：模块实为 strategies.factors.score_utils，
        # 原 strategies.factors.common 从不存在，ImportError 被静默吞掉后
        # 永远走简化 PE 档位——行业差异化阈值全部丢失。
        from strategies.factors.score_utils import pe_percentile

        pe_percentile_fn = pe_percentile
    except ImportError:
        pass

    if not quote:
        return 50.0
    pe = float(quote.get("pe") or 0)
    pb = float(quote.get("pb") or 0)
    growth = float(fin.get("net_profit_yoy") or fin.get("PARENTNETPROFITTZ") or 0) if fin else 0

    if pe <= 0 and pb <= 0:
        return 50.0

    score = 0.0
    if pe > 0:
        # pe_percentile 返回 0-100（越高越贵），反转为价值分（越高越便宜）
        score += 100 - pe_percentile_fn(pe, industry)
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
    trend = _safe_float(kline_features.get("trend"))
    if trend > 0:
        score += 20
    elif trend < 0:
        score -= 20

    rsi = _safe_float(kline_features.get("rsi"), 50.0)
    if 30 <= rsi <= 70:
        score += 5
    elif rsi > 80:
        score -= 15
    elif rsi < 20:
        score -= 5

    macd = _safe_float(kline_features.get("macd_signal"))
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
        elif advance_ratio < 0.2:  # 更严格阈值须先判，否则被 <0.3 吞没
            score -= 25
        elif advance_ratio < 0.3:
            score -= 15

    nh_nl_ratio = market_features.get("nh_nl_ratio", None)
    if nh_nl_ratio is not None:
        if nh_nl_ratio > 1.5:
            score += 10
        elif nh_nl_ratio < 0.2:  # 更严格阈值须先判
            score -= 20
        elif nh_nl_ratio < 0.5:
            score -= 10

    limit_up_count = _safe_float(market_features.get("limit_up_count"))
    if limit_up_count > 80:
        score += 15
    elif limit_up_count > 50:
        score += 10
    elif limit_up_count > 30:
        score += 5
    elif limit_up_count < 15:
        score -= 15

    limit_down_count = _safe_float(market_features.get("limit_down_count"))
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
    precomputed: Optional[Dict[str, float]] = None,
) -> Dict[str, object]:
    """通用 score_with_reasoning（v2.2.0）。

    把任一专家的 score() 包装成"含推理链"的版本，统一 buffett 的私有模式。
    原 buffett.py 的 score_with_reasoning 是手写 160 行；本通用模板让 13 位
    其他专家只需 1 行调用即可获得等价输出。

    Args:
        profile: 专家人设（含 5 维度权重 + display_name + group）
        score_fn: 专家的 score(stock_data) -> Dict[dim, 0-100]
        stock_data: 股票数据 dict
        precomputed: 已算好的 score 结果（v1.26.0）。传入可避免重复调用
            score_fn——合并型专家的 score() 内部已算过子专家，调用方若还需
            子评分就会重复计算（实测 value_anchor/institution 各被算 2 次）。

    Returns:
        {
            "scores": {dim: float, ...},
            "reasoning": [str, ...],
            "dimensions": {dim: {"score": float, "weight": float, "reason": str}, ...},
            "display_name": str,
            "expert_id": str,
        }
    """
    scores = precomputed if precomputed is not None else score_fn(stock_data)
    reasoning = []
    dimensions = {}

    for dim, score in scores.items():
        # （v1.26.0）权重查找要兼容别名维度：profile.weights 加载时已归一化
        # （"情绪/资金"→"情绪"），而 score() 返回的仍是别名原键——直接
        # get(dim) 会返回 0.0，推理链显示"权重 0%"，对用户是误导。
        weight = profile.weights.get(dim)
        if weight is None:
            weight = profile.weights.get(normalize_dim(dim), 0.0)
        weight = weight / 100.0
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
        "| 维度 | 权重 | 得分 | 评分依据 |",
        "|------|------|------|----------|",
    ]

    for dim, info in dimensions.items():
        lines.append(f"| {dim} | {info['weight']:.0%} | {info['score']:.0f} | {info['reason']} |")

    lines.append("")
    lines.append("## 关键判断")
    lines.append("")
    for r in reasoning:
        lines.append(f"- {r}")

    return "\n".join(lines)
