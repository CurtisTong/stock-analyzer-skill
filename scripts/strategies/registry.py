"""
策略注册表：管理策略定义和权重配置。
"""

import threading
from typing import Dict

# ---------- 内置策略定义 ----------
# 九因子：quality / valuation / momentum / liquidity / volatility / dividend / chip / event / analyst
# volatility 为 A 股低波动异象因子，低波动得高分
# dividend 为红利因子（2026新增），股息率+分红连续性+分红率稳定性
# chip 为筹码因子（2026新增），股东户数变化率+融资融券趋势
# event 为事件因子（待调优），当前权重 0.0
# analyst 为分析师预期因子（待调优），当前权重 0.0

# RLock 守护 STRATEGIES 全局 dict 的写路径；
# 外部 12+ 个读取点（strategy_performance.py / screener.py / screening_service.py / backtest/*）
# 暂未迁移到本 API，故保留 dict 直读以避免大范围 API 变更。
# 新代码请用 get_strategy() / list_strategies() 走锁路径。
_STRATEGIES_LOCK = threading.RLock()

STRATEGIES: Dict[str, dict] = {
    "balanced": {
        "quality": 0.28,
        "valuation": 0.19,
        "momentum": 0.14,
        "liquidity": 0.05,
        "volatility": 0.14,
        "dividend": 0.05,
        "chip": 0.10,
        "event": 0.05,  # (#10) 灰度上线 0.05
        "analyst": 0.0,
        "label": "均衡精选",
    },
    "quality_value": {
        "quality": 0.29,
        "valuation": 0.33,
        "momentum": 0.05,
        "liquidity": 0.05,
        "volatility": 0.09,
        "dividend": 0.09,
        "chip": 0.05,
        "event": 0.05,  # (#10) 灰度上线 0.05
        "analyst": 0.0,
        "label": "质量价值",
    },
    "growth_momentum": {
        "quality": 0.19,
        "valuation": 0.19,
        "momentum": 0.28,
        "liquidity": 0.09,
        "volatility": 0.05,
        "dividend": 0.05,
        "chip": 0.10,
        "event": 0.05,  # (#10) 灰度上线 0.05
        "analyst": 0.0,
        "label": "成长动量",
    },
    "defensive": {
        "quality": 0.21,
        "valuation": 0.19,
        "momentum": 0.05,
        "liquidity": 0.03,
        "volatility": 0.19,
        "dividend": 0.10,
        "chip": 0.18,
        "event": 0.05,  # (#10) 灰度上线 0.05
        "analyst": 0.0,
        "label": "防守低波",
    },
    "turning_point": {
        "quality": 0.19,
        "valuation": 0.19,
        "momentum": 0.14,
        "liquidity": 0.10,
        "volatility": 0.14,
        "dividend": 0.09,
        "chip": 0.10,
        "event": 0.05,  # (#10) 灰度上线 0.05
        "analyst": 0.0,
        "label": "拐点修复",
        "two_stage": True,
    },
    "ma_volume_momentum": {
        "quality": 0.14,
        "valuation": 0.14,
        "momentum": 0.33,
        "liquidity": 0.14,
        "volatility": 0.05,
        "dividend": 0.05,
        "chip": 0.10,
        "event": 0.05,  # (#10) 灰度上线 0.05
        "analyst": 0.0,
        "label": "量价动量",
    },
}


# ---------- 策略注册 API ----------


def register_strategy(
    name: str, weights: dict, label: str = "", replace: bool = False
) -> None:
    """注册新策略。

    Args:
        name: 策略名称
        weights: 因子权重 dict，需包含 quality/valuation/momentum/liquidity
                 volatility 和 dividend 为可选因子（默认 0）
        label: 策略中文标签
        replace: 是否允许覆盖已存在策略（默认 False，保护已注册策略不可变）。

    Raises:
        ValueError: 权重缺失必需键 / 权重和不等于 1.0 / 重复注册（replace=False）
    """
    weights = {**weights}
    with _STRATEGIES_LOCK:
        required_keys = {"quality", "valuation", "momentum", "liquidity"}
        if not required_keys.issubset(weights.keys()):
            raise ValueError(f"策略权重必须包含 {required_keys}")
        for opt_key in (
            "volatility",
            "dividend",
            "chip",
            "event",
            "analyst",
            "cyclical",
        ):
            if opt_key not in weights:
                weights[opt_key] = 0.0
        all_keys = required_keys | {
            "volatility",
            "dividend",
            "chip",
            "event",
            "analyst",
            "cyclical",
        }
        total = sum(weights.get(k, 0) for k in all_keys)
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"权重之和应为 1.0，当前为 {total}")
        if name in STRATEGIES and not replace:
            raise ValueError(
                f"策略 {name!r} 已注册；如需覆盖请显式传 replace=True（保护全局状态不被并发修改）"
            )
        STRATEGIES[name] = {**weights, "label": label or name}


def get_strategy(name: str) -> dict:
    """获取策略配置。"""
    with _STRATEGIES_LOCK:
        if name not in STRATEGIES:
            raise KeyError(f"未知策略: {name}，可用: {list(STRATEGIES.keys())}")
        return STRATEGIES[name]


def list_strategies() -> list:
    """列出所有策略名称。"""
    with _STRATEGIES_LOCK:
        return list(STRATEGIES.keys())


def strategy_exists(name: str) -> bool:
    """检查策略是否已注册（锁内 membership 测试，P2-09 替代直接 STRATEGIES 直读）。"""
    with _STRATEGIES_LOCK:
        return name in STRATEGIES
