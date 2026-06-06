"""
策略注册表：管理策略定义和权重配置。
"""
from typing import Dict, Optional

# ---------- 内置策略定义 ----------

STRATEGIES: Dict[str, dict] = {
    "balanced": {
        "quality": 0.32,
        "valuation": 0.25,
        "momentum": 0.23,
        "liquidity": 0.20,
        "label": "均衡精选",
    },
    "quality_value": {
        "quality": 0.42,
        "valuation": 0.32,
        "momentum": 0.10,
        "liquidity": 0.16,
        "label": "质量价值",
    },
    "growth_momentum": {
        "quality": 0.26,
        "valuation": 0.12,
        "momentum": 0.42,
        "liquidity": 0.20,
        "label": "成长动量",
    },
    "defensive": {
        "quality": 0.38,
        "valuation": 0.34,
        "momentum": 0.08,
        "liquidity": 0.20,
        "label": "防守低波",
    },
    "turning_point": {
        "quality": 0.24,
        "valuation": 0.24,
        "momentum": 0.36,
        "liquidity": 0.16,
        "label": "拐点修复",
    },
}


# ---------- 策略注册 API ----------

def register_strategy(name: str, weights: dict, label: str = "") -> None:
    """注册新策略。

    Args:
        name: 策略名称
        weights: 因子权重 dict，需包含 quality/valuation/momentum/liquidity
        label: 策略中文标签
    """
    required_keys = {"quality", "valuation", "momentum", "liquidity"}
    if not required_keys.issubset(weights.keys()):
        raise ValueError(f"策略权重必须包含 {required_keys}")
    total = sum(weights[k] for k in required_keys)
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
