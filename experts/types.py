"""专家系统类型定义。"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class ExpertProfile:
    """专家人设的结构化档案。"""

    name: str  # 英文短名（e.g. "buffett"）
    display_name: str  # 中文显示名（e.g. "巴菲特"）
    group: str  # "long_term" | "short_term"
    style: str  # 风格标签（e.g. "价值投资"）
    horizon: str  # 持仓周期（e.g. "月/季/年"）
    core_signal: str  # 核心信号源
    weights: Dict[str, float]  # 5 维度权重（百分比，加和 100）
    veto_conditions: List[str] = field(default_factory=list)
    md_path: str = ""  # 关联的 markdown 路径
    active: bool = True  # v2.1.0 起：False 表示 deprecated，新框架不再调用


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
