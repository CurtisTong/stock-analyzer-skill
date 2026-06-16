"""合并型专家评分工具。

v2.1.0 起：value_anchor/topic_leader/emotion_tech 三个合并 profile
通过调用对应 legacy 函数的加权平均实现，确保新视角继承原专家的
所有阈值逻辑（而不是简化版骨架）。
"""
from typing import Dict, List


def weighted_merge(
    expert_results: List[Dict[str, float]],
    weights: List[float] = None,
) -> Dict[str, float]:
    """把多个 expert 的 dim_scores 按权重合并。

    Args:
        expert_results: 每个 expert 的 {dim: 0-100 score}
        weights: 对应每个 expert 的权重，默认等权

    Returns:
        {dim: 0-100} 加权平均后的维度分

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
    assert len(weights) == len(expert_results), "weights 与 expert_results 长度不一致"
    total_w = sum(weights)
    weights = [w / total_w for w in weights]  # 归一化

    # 收集所有维度
    all_dims = set()
    for r in expert_results:
        all_dims.update(r.keys())

    merged = {}
    for dim in all_dims:
        weighted_sum = 0.0
        for r, w in zip(expert_results, weights):
            v = r.get(dim, 50.0)  # 缺失维度用中性 50
            weighted_sum += v * w
        merged[dim] = round(max(0.0, min(100.0, weighted_sum)), 1)

    return merged