"""
情绪技术复合（合并炒股养家+作手新一）评分函数 v2.1.1。

v2.1.0：骨架实现
v2.1.1：调 chaogu_yangjia + zuoshou_xinyi 加权平均

人设：情绪周期 + K线反转形态。
"""
from typing import Dict


def score(stock_data: dict) -> Dict[str, float]:
    """情绪技术复合：养家 0.5 + 作手新一 0.5 加权平均。"""
    from . import chaogu_yangjia, zuoshou_xinyi
    from ._merge import weighted_merge

    return weighted_merge(
        [chaogu_yangjia.score(stock_data), zuoshou_xinyi.score(stock_data)],
        weights=[0.5, 0.5],
    )


def score_with_reasoning(stock_data: dict) -> Dict[str, object]:
    """情绪技术复合评分（含推理链）。

    v2.2.0 起统一使用 generic_score_with_reasoning 模板。
    """
    from experts.registry import EXPERT_REGISTRY
    from ._utils import generic_score_with_reasoning
    profile = EXPERT_REGISTRY["emotion_tech"]
    return generic_score_with_reasoning(profile, score, stock_data)