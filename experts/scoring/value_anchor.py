"""
价值双锚（合并巴菲特+段永平）评分函数 v2.1.2。

v2.1.0：骨架实现
v2.1.1：调 buffett + duan_yongping 加权平均，确保继承原逻辑
v2.1.2：输出 buffett_sub_score 子评分，供 vote_engine 判断否决权
v2.3.1：从 registry 动态读取 buffett 权重，避免硬编码漂移

人设：美式数据 + 中式文化，强调 ROE/PE + 商业模式 + 安全边际。
"""

from typing import Dict


def _get_buffett_weights() -> Dict[str, float]:
    """从注册表动态获取巴菲特的维度权重。"""
    from experts.registry import EXPERT_REGISTRY

    buffett_profile = EXPERT_REGISTRY.get("buffett")
    if buffett_profile is not None:
        return {dim: w / 100.0 for dim, w in buffett_profile.weights.items()}
    # 回退：buffett 未注册时使用默认权重
    return {
        "基本面": 0.42,
        "估值": 0.28,
        "技术面": 0.05,
        "情绪": 0.05,
        "安全边际": 0.20,
    }


def _compute_buffett_sub_score(buffett_dims: Dict[str, float]) -> float:
    """用巴菲特的权重计算加权总分。"""
    weights = _get_buffett_weights()
    return round(
        sum(buffett_dims.get(dim, 0) * w for dim, w in weights.items()),
        1,
    )


def score(stock_data: dict) -> Dict[str, float]:
    """价值双锚：巴菲特 0.55 + 段永平 0.45 加权平均。"""
    from . import buffett, duan_yongping
    from ._merge import weighted_merge

    # 只调用一次 buffett.score，避免重复计算
    buffett_dims = buffett.score(stock_data)
    duan_dims = duan_yongping.score(stock_data)
    result = weighted_merge(
        [buffett_dims, duan_dims],
        weights=[0.55, 0.45],
    )
    # P1-17: score() 也输出 buffett_sub_score，使 score_expert_precise（SKILL.md 推荐
    # 量化基线路径，调用 score() 而非 score_with_reasoning）能正确判断巴菲特否决权，
    # 避免 v2.1.2 否决权隔离在推荐路径下静默失效。
    result["buffett_sub_score"] = _compute_buffett_sub_score(buffett_dims)
    return result


def score_with_reasoning(stock_data: dict) -> Dict[str, object]:
    """价值双锚评分（含推理链 + 巴菲特子评分）。

    v2.1.2 起：输出 buffett_sub_score 字段，供 vote_engine
    在合并型专家场景下仍能正确判断巴菲特否决权（≤39 触发）。
    否决权不应被段永平的看多稀释——这是架构层面的设计修正。
    """
    from experts.registry import EXPERT_REGISTRY
    from ._utils import generic_score_with_reasoning
    from . import buffett

    profile = EXPERT_REGISTRY["value_anchor"]
    result = generic_score_with_reasoning(profile, score, stock_data)

    # 计算巴菲特独立子评分（加权总分），供否决权判断
    buffett_dims = buffett.score(stock_data)
    result["buffett_sub_score"] = _compute_buffett_sub_score(buffett_dims)

    return result
