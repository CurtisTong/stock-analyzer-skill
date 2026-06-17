"""
策略注册表：管理策略定义和权重配置。
"""

from typing import Dict, Optional

# ---------- 内置策略定义 ----------
# 六因子：quality / valuation / momentum / liquidity / volatility / dividend
# volatility 为 A 股低波动异象因子，低波动得高分
# dividend 为红利因子（2026新增），股息率+分红连续性+分红率稳定性

STRATEGIES: Dict[str, dict] = {
    "balanced": {
        "quality": 0.23,
        "valuation": 0.18,
        "momentum": 0.18,
        "liquidity": 0.14,
        "volatility": 0.18,
        "dividend": 0.09,
        "label": "均衡精选",
    },
    "quality_value": {
        "quality": 0.32,
        "valuation": 0.28,
        "momentum": 0.05,
        "liquidity": 0.10,
        "volatility": 0.15,
        "dividend": 0.10,
        "label": "质量价值",
    },
    "growth_momentum": {
        "quality": 0.18,
        "valuation": 0.15,
        "momentum": 0.35,
        "liquidity": 0.12,
        "volatility": 0.18,
        "dividend": 0.02,
        "label": "成长动量",
    },
    "defensive": {
        "quality": 0.22,
        "valuation": 0.20,
        "momentum": 0.06,
        "liquidity": 0.10,
        "volatility": 0.28,
        "dividend": 0.14,
        "label": "防守低波",
    },
    "turning_point": {
        "quality": 0.18,
        "valuation": 0.18,
        "momentum": 0.30,
        "liquidity": 0.14,
        "volatility": 0.16,
        "dividend": 0.04,
        "label": "拐点修复",
    },
}


# ---------- 策略注册 API ----------


def register_strategy(name: str, weights: dict, label: str = "") -> None:
    """注册新策略。

    Args:
        name: 策略名称
        weights: 因子权重 dict，需包含 quality/valuation/momentum/liquidity
                 volatility 和 dividend 为可选因子（默认 0）
        label: 策略中文标签
    """
    weights = {**weights}
    required_keys = {"quality", "valuation", "momentum", "liquidity"}
    if not required_keys.issubset(weights.keys()):
        raise ValueError(f"策略权重必须包含 {required_keys}")
    for opt_key in ("volatility", "dividend"):
        if opt_key not in weights:
            weights[opt_key] = 0.0
    all_keys = required_keys | {"volatility", "dividend"}
    total = sum(weights.get(k, 0) for k in all_keys)
    if abs(total - 1.0) > 0.01:
        raise ValueError(f"权重之和应为 1.0，当前为 {total}")
    STRATEGIES[name] = {**weights, "label": label or name}


def get_strategy(name: str) -> dict:
    """获取策略配置。"""
    if name not in STRATEGIES:
        raise KeyError(f"未知策略: {name}，可用: {list(STRATEGIES.keys())}")
    return STRATEGIES[name]


def list_strategies() -> list:
    """列出所有策略名称。"""
    return list(STRATEGIES.keys())
