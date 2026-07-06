"""合并型专家评分工具。

v2.1.0 起：value_anchor/topic_leader/emotion_tech 三个合并 profile
通过调用对应 legacy 函数的加权平均实现，确保新视角继承原专家的
所有阈值逻辑（而不是简化版骨架）。

v2.3.0：增加 veto 逻辑——如果任一子专家某维度触发否决（score < 20），
合并后该维度取最低分而非加权平均，避免否决条件被稀释。
"""

from typing import Dict, List

# 否决阈值：子专家某维度低于此分数时，视为触发否决
_VETO_THRESHOLD = 10.0


def weighted_merge(
    expert_results: List[Dict[str, float]],
    weights: List[float] = None,
    enable_veto: bool = True,
) -> Dict[str, float]:
    """把多个 expert 的 dim_scores 按权重合并。

    否决逻辑：如果任一子专家某维度 score < 10（触发否决），
    合并后该维度取最低分，而非加权平均。这保留了原专家的
    否决条件（如 Buffett 的 ROE<10% 否决、FCF 连续为负否决）。

    Args:
        expert_results: 每个 expert 的 {dim: 0-100 score}
        weights: 对应每个 expert 的权重，默认等权

    Returns:
        {dim: 0-100} 加权平均后的维度分（否决维度取最低分）

    Example:
        >>> weighted_merge(
        ...     [buffett.score(data), duan_yongping.score(data)],
        ...     weights=[0.5, 0.5],
        ... )
    """
    if not expert_results:
        return {}

    if weights is None:
        weights = [1.0 / len(expert_results)] * len(expert_results)
    if len(weights) != len(expert_results):
        raise ValueError(
            f"weights 长度({len(weights)})与 expert_results 长度({len(expert_results)})不一致"
        )
    total_w = sum(weights)
    weights = [w / total_w for w in weights]  # 归一化

    # 收集所有维度
    all_dims = set()
    for r in expert_results:
        all_dims.update(r.keys())

    merged = {}
    for dim in all_dims:
        scores = [r.get(dim, 50.0) for r in expert_results]
        min_score = min(scores)
        # 否决检查：任一子专家该维度 < 阈值 → 取最低分
        if enable_veto and min_score < _VETO_THRESHOLD:
            merged[dim] = round(max(0.0, min_score), 1)
        else:
            weighted_sum = sum(v * w for v, w in zip(scores, weights))
            merged[dim] = round(max(0.0, min(100.0, weighted_sum)), 1)

    return merged
