"""
8 人专家圆桌 · 可调用 API。

本模块把 experts/*.md 的人设和评分矩阵沉淀为 Python 数据结构，
使 `stock` skill 的 debate 模式可在代码层查询专家维度权重和一票否决条件。

公开 API：
- EXPERT_REGISTRY: Dict[expert_name, ExpertProfile]
- get_expert(name) -> ExpertProfile | None
- list_experts(group=None) -> List[ExpertProfile]
- list_long_term_experts() -> List[ExpertProfile]
- list_short_term_experts() -> List[ExpertProfile]
- direction_from_score(score) -> str
- apply_veto(profile, stock_data, veto_results=None) -> List[str]

每位专家的人设、案例、引用仍以 experts/<name>.md 为权威来源，
本模块只承载结构化字段（权重 + 否决条件 + 标签）。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ExpertProfile:
    """专家人设的结构化档案。"""
    name: str                       # 英文短名（e.g. "buffett"）
    display_name: str               # 中文显示名（e.g. "巴菲特"）
    group: str                      # "long_term" | "short_term"
    style: str                      # 风格标签（e.g. "价值投资"）
    horizon: str                    # 持仓周期（e.g. "月/季/年"）
    core_signal: str                # 核心信号源
    weights: Dict[str, float]       # 5 维度权重（百分比，加和 100）
    veto_conditions: List[str] = field(default_factory=list)
    md_path: str = ""               # 关联的 markdown 路径


# 方向判定阈值（与 experts/decide.md §一.1.1 一致）
DIRECTION_THRESHOLDS = [
    (70, "强烈看多"),
    (60, "看多"),
    (40, "中性"),
    (30, "看空"),
    (0, "强烈看空"),
]


def direction_from_score(score: float) -> str:
    """把 0-100 总分映射到方向标签。"""
    for threshold, label in DIRECTION_THRESHOLDS:
        if score >= threshold:
            return label
    return "强烈看空"


def apply_veto(
    profile: ExpertProfile,
    stock_data: dict,
    veto_results: Optional[Dict[str, bool]] = None,
) -> List[str]:
    """根据股票数据检查专家的一票否决条件。

    Args:
        profile: 专家人设档案
        stock_data: 股票数据（quote + finance 字段）
        veto_results: 预判的否决条件结果 dict（key 是条件描述，value 是
            bool，True 表示"已触发"）。为 None 时返回全部条件列表
            （不预判，留给调用方处理）。

    Returns:
        已触发的否决条件描述列表。
    """
    if veto_results is None:
        return list(profile.veto_conditions)
    return [cond for cond, triggered in veto_results.items() if triggered]


# 导入注册表（放在模块底部以利用 dataclass 定义）
from .registry import EXPERT_REGISTRY, LEGACY_ALIAS, get_display_name, _ensure_loaded  # noqa: E402

_ensure_loaded()


def get_expert(name: str) -> Optional[ExpertProfile]:
    """按英文短名获取专家档案。"""
    return EXPERT_REGISTRY.get(name)


def list_experts(group: Optional[str] = None) -> List[ExpertProfile]:
    """列出专家。group 过滤：None=全部 / "long_term" / "short_term"。"""
    all_experts = list(EXPERT_REGISTRY.values())
    if group is None:
        return all_experts
    return [e for e in all_experts if e.group == group]


def list_long_term_experts() -> List[ExpertProfile]:
    """长线 4 人：巴菲特 / 林奇 / 索罗斯 / 段永平。"""
    return list_experts("long_term")


def list_short_term_experts() -> List[ExpertProfile]:
    """短线 4 人：徐翔 / 赵老哥 / 养家 / 作手新一。"""
    return list_experts("short_term")


__all__ = [
    "ExpertProfile",
    "EXPERT_REGISTRY",
    "LEGACY_ALIAS",
    "get_display_name",
    "get_expert",
    "list_experts",
    "list_long_term_experts",
    "list_short_term_experts",
    "direction_from_score",
    "apply_veto",
    "DIRECTION_THRESHOLDS",
]
