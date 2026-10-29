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

    # 单资产上限钳制（若命中，超出部分按比例回分给未超限资产）
    if cap_pct < 100.0:
        capped = {k: w for k, w in weights.items() if w > cap_pct}
        if capped:
            excess = sum(w - cap_pct for w in capped.values())
            for k in capped:
                weights[k] = cap_pct
            free = [k for k in weights if k not in capped]
            free_total = sum(weights[k] for k in free) or 1.0
            if free:
                for k in free:
                    weights[k] += excess * weights[k] / free_total

    return {k: round(w, 2) for k, w in weights.items()}


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
