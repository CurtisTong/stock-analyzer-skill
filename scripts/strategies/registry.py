"""
策略注册表：管理策略定义和权重配置。
"""

from typing import Dict, Optional

# ---------- 内置策略定义 ----------
# 九因子：quality / valuation / momentum / liquidity / volatility / dividend / chip / event / analyst
# volatility 为 A 股低波动异象因子，低波动得高分
# dividend 为红利因子（2026新增），股息率+分红连续性+分红率稳定性
# chip 为筹码因子（2026新增），股东户数变化率+融资融券趋势
# event 为事件因子（待调优），当前权重 0.0
# analyst 为分析师预期因子（待调优），当前权重 0.0

STRATEGIES: Dict[str, dict] = {
    "balanced": {
        "quality": 0.30,
        "valuation": 0.20,
        "momentum": 0.15,
        "liquidity": 0.05,
        "volatility": 0.15,
        "dividend": 0.05,
        "chip": 0.10,
        "event": 0.0,
        "analyst": 0.0,
        "label": "均衡精选",
    },
    "quality_value": {
        "quality": 0.30,
        "valuation": 0.35,
        "momentum": 0.05,
        "liquidity": 0.05,
        "volatility": 0.10,
        "dividend": 0.10,
        "chip": 0.05,
        "event": 0.0,
        "analyst": 0.0,
        "label": "质量价值",
    },
    "growth_momentum": {
        "quality": 0.20,
        "valuation": 0.20,
        "momentum": 0.30,
        "liquidity": 0.10,
        "volatility": 0.05,
        "dividend": 0.05,
        "chip": 0.10,
        "event": 0.0,
        "analyst": 0.0,
        "label": "成长动量",
    },
    "defensive": {
        "quality": 0.22,
        "valuation": 0.20,
        "momentum": 0.05,
        "liquidity": 0.03,
        "volatility": 0.20,
        "dividend": 0.10,
        "chip": 0.20,
        "event": 0.0,
        "analyst": 0.0,
        "label": "防守低波",
    },
    "turning_point": {
        "quality": 0.20,
        "valuation": 0.20,
        "momentum": 0.15,
        "liquidity": 0.10,
        "volatility": 0.15,
        "dividend": 0.10,
        "chip": 0.10,
        "event": 0.0,
        "analyst": 0.0,
        "label": "拐点修复",
        "two_stage": True,
    },
    "ma_volume_momentum": {
        "quality": 0.15,
        "valuation": 0.15,
        "momentum": 0.35,
        "liquidity": 0.15,
        "volatility": 0.05,
        "dividend": 0.05,
        "chip": 0.10,
        "event": 0.0,
        "analyst": 0.0,
        "label": "量价动量",
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
    for opt_key in ("volatility", "dividend", "chip"):
        if opt_key not in weights:
            weights[opt_key] = 0.0
    all_keys = required_keys | {"volatility", "dividend", "chip"}
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
