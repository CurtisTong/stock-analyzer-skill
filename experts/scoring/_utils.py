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


__all__ = [
    "_safe_float",
    "_get_clamp",
    "_get_scoring_config",
    "score_from_dimensions",
    "dimension_breakdown",
]
