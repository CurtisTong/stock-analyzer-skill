"""专家系统类型定义。"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List

logger = logging.getLogger(__name__)


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

    def __post_init__(self) -> None:
        """校验权重加和是否接近 100（允许浮点误差 ±0.5）。"""
        total = sum(self.weights.values())
        if abs(total - 100.0) > 0.5:
            logger.warning(
                "专家 %s 权重加和 = %.1f（期望 100），维度: %s",
                self.name,
                total,
                list(self.weights.keys()),
            )


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


# ═══════════════════════════════════════════════════════════════
# 维度名别名归一化（C1 / P1-7）
# 不同专家的 score() 可能返回非标准维度名（如"情绪/反身性"、"情绪/题材"、
# "情绪/资金"），聚合时需归一到标准 5 维度（基本面/估值/技术面/情绪/风险），
# 否则 weighted_merge 会把别名当成独立维度，导致权重查找失败。
# ═══════════════════════════════════════════════════════════════

DIMENSION_ALIASES: Dict[str, str] = {
    # 情绪维度别名
    "情绪/资金": "情绪",
    "资金/情绪": "情绪",
    "情绪/反身性": "情绪",
    "情绪/题材": "情绪",
    # 资金维度别名（部分专家用"资金面"替代）
    "资金面": "资金",
    # 估值/质量别名
    "估值/质量": "估值",
    "质量/估值": "质量",
    # 技术/趋势别名（标准名为"技术面"）
    "技术/趋势": "技术面",
    "趋势/技术": "技术面",
    "技术面/趋势": "技术面",
}


def normalize_dim(name: str) -> str:
    """把维度名别名映射到标准名称；非别名原样返回。

    用于 score_from_dimensions / weighted_merge 入口归一化，使各专家 score()
    返回的人设特色维度名（保持叙事）在聚合时按同一标准维度合并。
    """
    return DIMENSION_ALIASES.get(name, name)
