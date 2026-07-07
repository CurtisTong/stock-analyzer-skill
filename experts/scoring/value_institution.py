"""
价值机构锚（合并 value_anchor + institution）评分函数 v2.4.0。

v2.4.0：将 value_anchor（巴菲特0.55+段永平0.45）与 institution（机构派）
按 0.5:0.5 加权合并，消除 90% 权重同构的"伪多元化"。

合并逻辑：
- value_anchor 权重 0.5：保留巴菲特否决警示（buffett_sub_score）
- institution 权重 0.5：保留机构派独特视角（商业模式可持续性、行业天花板、治理信号）
- veto_conditions 取两者并集
- 输出 buffett_sub_score + institution_sub_score 双子评分

人设：价值双锚 + 机构长期主义，强调 ROE/PE/FCF + 商业模式 + 行业空间 + 公司治理。
"""

from typing import Dict


def _get_buffett_weights() -> Dict[str, float]:
    """从注册表动态获取巴菲特的维度权重。"""
    from experts.registry import EXPERT_REGISTRY

    buffett_profile = EXPERT_REGISTRY.get("buffett")
    if buffett_profile is not None:
        return {dim: w / 100.0 for dim, w in buffett_profile.weights.items()}
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
    """价值机构锚：value_anchor 0.5 + institution 0.5 加权平均。

    value_anchor 本身是 buffett(0.55) + duan_yongping(0.45) 的合并，
    因此最终权重链为：
      buffett: 0.5 * 0.55 = 0.275
      duan_yongping: 0.5 * 0.45 = 0.225
      institution: 0.5
    """
    from . import value_anchor, institution
    from ._merge import weighted_merge

    # 调用两个子专家的评分
    va_dims = value_anchor.score(stock_data)
    inst_dims = institution.score(stock_data)
    result = weighted_merge(
        [va_dims, inst_dims],
        weights=[0.5, 0.5],
    )

    # 保留巴菲特否决警示所需的独立子评分
    # value_anchor.score 内部已计算 buffett_sub_score，直接透传
    result["buffett_sub_score"] = va_dims.get("buffett_sub_score", 50.0)

    # 新增 institution 独立子评分，供 veto 判断
    # 用 institution 的权重计算加权总分
    from experts.registry import EXPERT_REGISTRY
    inst_profile = EXPERT_REGISTRY.get("institution")
    if inst_profile is not None:
        inst_weights = {dim: w / 100.0 for dim, w in inst_profile.weights.items()}
        inst_sub = sum(inst_dims.get(dim, 0) * w for dim, w in inst_weights.items())
        result["institution_sub_score"] = round(inst_sub, 1)
    else:
        result["institution_sub_score"] = 50.0

    return result


def score_with_reasoning(stock_data: dict) -> Dict[str, object]:
    """价值机构锚评分（含推理链 + 双子评分）。

    输出 buffett_sub_score + institution_sub_score 字段，
    供 vote_engine 在合并型专家场景下正确判断否决权。
    """
    from experts.registry import EXPERT_REGISTRY
    from ._utils import generic_score_with_reasoning
    from . import value_anchor, institution

    profile = EXPERT_REGISTRY["value_institution"]
    result = generic_score_with_reasoning(profile, score, stock_data)

    # 透传双子评分
    va_dims = value_anchor.score(stock_data)
    result["buffett_sub_score"] = va_dims.get("buffett_sub_score", 50.0)

    inst_dims = institution.score(stock_data)
    inst_profile = EXPERT_REGISTRY.get("institution")
    if inst_profile is not None:
        inst_weights = {dim: w / 100.0 for dim, w in inst_profile.weights.items()}
        inst_sub = sum(inst_dims.get(dim, 0) * w for dim, w in inst_weights.items())
        result["institution_sub_score"] = round(inst_sub, 1)
    else:
        result["institution_sub_score"] = 50.0

    return result
