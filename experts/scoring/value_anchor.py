"""
价值双锚（合并巴菲特+段永平）评分函数 v2.1.1。

v2.1.0：骨架实现
v2.1.1：调 buffett + duan_yongping 加权平均，确保继承原逻辑

人设：美式数据 + 中式文化，强调 ROE/PE + 商业模式 + 安全边际。
"""
from typing import Dict


def score(stock_data: dict) -> Dict[str, float]:
    """价值双锚：巴菲特 0.55 + 段永平 0.45 加权平均。"""
    from . import buffett, duan_yongping
    from ._merge import weighted_merge

    return weighted_merge(
        [buffett.score(stock_data), duan_yongping.score(stock_data)],
        weights=[0.55, 0.45],
    )


def score_with_reasoning(stock_data: dict) -> Dict[str, object]:
    """价值双锚评分（含推理链）。

    v2.2.0 起统一使用 generic_score_with_reasoning 模板。
    """
    from experts.registry import EXPERT_REGISTRY
    from ._utils import generic_score_with_reasoning
    profile = EXPERT_REGISTRY["value_anchor"]
    return generic_score_with_reasoning(profile, score, stock_data)