"""组合层风险加权建议（v1.24.0，对标 PyPortfolioOpt/Lean RiskParity）。

逆波动率加权（inverse volatility）：权重 ∝ 1/σ_i，再归一化。
低波动资产获得更大权重——不依赖协方差矩阵，只需每只股票的
收益波动率，与零依赖原则兼容（纯 stdlib + get_kline）。

这是等权分配的轻量升级；风险平价（需要协方差分解）保留为
未来选项（报告 P2 第 9 项递延）。
"""

from __future__ import annotations

import statistics


def inverse_volatility_weights(
    volatilities: dict[str, float],
    cap_pct: float = 100.0,
) -> dict[str, float]:
    """逆波动率加权。

    Args:
        volatilities: {code: 日收益标准差}（年化与否不影响权重，需 > 0）
        cap_pct: 单资产权重上限（%），默认 100 = 不设上限

    Returns:
        {code: 权重 %}（归一化到 100%）

    Raises:
        ValueError: volatilities 为空、全为非正，或无正波动率资产
    """
    if not volatilities:
        raise ValueError("volatilities 为空，无法计算权重")
    pos = {k: v for k, v in volatilities.items() if v and v > 0}
    if not pos:
        raise ValueError("无正波动率资产，无法计算逆波动率权重")

    inv = {k: 1.0 / v for k, v in pos.items()}
    total = sum(inv.values())
    weights = {k: v / total * 100.0 for k, v in inv.items()}

    # 单资产上限钳制（若命中，超出部分回分给未超限资产）
    # 用水填充（iterative proportional fitting）：超额部分按各自由资产的
    # "剩余容量"（cap - 当前权重）比例分配，而不是按当前权重比例——后者会
    # 振荡不收敛（实测：低波 0.8 / 高波 4.0 / 中波 1.0，cap=40 反复互推，
    # 最终仍有 40.75% 突破上限）。
    if cap_pct < 100.0:
        eps = 1e-9
        for _ in range(len(weights) * 4 + 8):
            capped = {k: w for k, w in weights.items() if w > cap_pct + eps}
            if not capped:
                break
            excess = sum(w - cap_pct for w in capped.values())
            for k in capped:
                weights[k] = cap_pct
            free = [k for k in weights if k not in capped]
            capacities = {k: max(0.0, cap_pct - weights[k]) for k in free}
            cap_sum = sum(capacities.values())
            if not free or cap_sum <= eps:
                # 无剩余容量可承接：约束不可行，权重和 < 100（剩余留现金）
                break
            if excess >= cap_sum:
                # 超额超过总容量：按容量全部分配（下一轮继续钳制）
                for k in free:
                    weights[k] += capacities[k]
            else:
                for k in free:
                    weights[k] += excess * capacities[k] / cap_sum

    return _round_to_total(weights, sum(weights.values()))


def _round_to_total(weights: dict[str, float], total: float = 100.0) -> dict[str, float]:
    """四舍五入到两位并把舍入误差补回最大权重项，保证权重和精确等于 total。

    逐项 round(2) 会让权重和漂移（实测 300 组随机用例中 37.7% 不等于 100.00）。
    """
    rounded = {k: round(w, 2) for k, w in weights.items()}
    if not rounded:
        return rounded
    diff = round(total - sum(rounded.values()), 2)
    if diff:
        # 补到权重最大的项（误差最小且不改变排序）
        k = max(rounded, key=lambda x: rounded[x])
        rounded[k] = round(rounded[k] + diff, 2)
    return rounded


def daily_volatility_from_closes(closes: list[float]) -> float | None:
    """日收益标准差（%）。

    Args:
        closes: 收盘价序列（至少 3 根）

    Returns:
        日波动率（%），样本不足或无变化返回 None
    """
    if len(closes) < 3:
        return None
    returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes)) if closes[i - 1] > 0]
    if len(returns) < 2:
        return None
    std = statistics.stdev(returns)
    if std <= 0:
        return None
    return std * 100


__all__ = ["inverse_volatility_weights", "daily_volatility_from_closes"]
