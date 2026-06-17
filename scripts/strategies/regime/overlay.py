"""
Overlay 权重调节：4 状态 × 6 因子 调节系数矩阵。

调节后权重：
  adjusted = original_weight × multiplier
  重新归一化到 1.0

设计原则（doc#03）：
  bull:  动量 +30%, 估值 -10%
  bear:  质量 +20%, 波动 +20%, 动量 -30%
  range: 质量 +10%, 估值 +10%, 动量 -20%
  panic: 质量 +30%, 波动 +30%, 动量 -50%, 流动性 +20%
"""

from typing import Dict

from .classifier import RegimeState

# 6 因子顺序：quality / valuation / momentum / liquidity / volatility / dividend
OVERLAY_MATRIX: Dict[RegimeState, Dict[str, float]] = {
    RegimeState.BULL: {
        "quality": 1.0,
        "valuation": 0.9,
        "momentum": 1.3,
        "liquidity": 1.0,
        "volatility": 1.0,
        "dividend": 1.0,
    },
    RegimeState.BEAR: {
        "quality": 1.2,
        "valuation": 1.0,
        "momentum": 0.7,
        "liquidity": 1.0,
        "volatility": 1.2,
        "dividend": 1.0,
    },
    RegimeState.RANGE: {
        "quality": 1.1,
        "valuation": 1.1,
        "momentum": 0.8,
        "liquidity": 1.0,
        "volatility": 1.0,
        "dividend": 1.0,
    },
    RegimeState.PANIC: {
        "quality": 1.3,
        "valuation": 1.0,
        "momentum": 0.5,
        "liquidity": 1.2,
        "volatility": 1.3,
        "dividend": 1.1,
    },
}


def compute_overlay_weights(
    original_weights: Dict[str, float], regime: RegimeState
) -> Dict[str, float]:
    """对原策略权重施加市场状态 overlay，返回归一化后的新权重。

    Args:
        original_weights: 策略原权重 dict（含 quality/valuation/momentum/liquidity/volatility/dividend）
        regime: 市场状态枚举

    Returns:
        调节并归一化后的新权重 dict（和 = 1.0）
    """
    multipliers = OVERLAY_MATRIX[regime]
    adjusted = {}
    for k, v in original_weights.items():
        if k in ("label", "two_stage"):
            continue
        mult = multipliers.get(k, 1.0)
        adjusted[k] = v * mult

    total = sum(adjusted.values())
    if total <= 0:
        return original_weights

    return {k: round(v / total, 4) for k, v in adjusted.items()}
