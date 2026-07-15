"""
Overlay 权重调节：4 状态 × 9 因子 调节系数矩阵。

调节后权重：
  adjusted = original_weight × multiplier
  重新归一化到 1.0

设计原则（doc#03）：
  bull:  动量 +30%, 估值 -10%
  bear:  质量 +20%, 波动 +20%, 动量 -30%
  range: 质量 +10%, 估值 +10%, 动量 -20%
  panic: 质量 +30%, 波动 +30%, 动量 -50%, 流动性 +20%

v2.x (#7)：矩阵从硬编码改为读取 config/regime_weight_map.yaml，
支持研究员基于回测结果调优而无需修改业务代码。
配置缺失时回退硬编码默认值（向后兼容）。

v2.8 新增 extreme_drop：极端跌幅（单日 <-5%）时 momentum 强制 ×0.3，
                    防止动量因子在崩盘次日延续错误的趋势信号。
v2.9 新增 national_team：国家队 ETF 放量（沪深 300/中证 500）时 chip
                    multiplier 不低于 0.6——国家队行为会扭曲筹码分布信号。
v3.0 新增 ic_multipliers：因子 IC 动态调整 multiplier，IC<0 因子
                    线性衰减至 min_mult(0.5)，IC>0 保持基础值。
"""

import logging
from typing import Dict, Optional

from .classifier import RegimeState

logger = logging.getLogger(__name__)

# 9 因子顺序：quality / valuation / momentum / liquidity / volatility / dividend / chip / event / analyst

# 硬编码默认矩阵（配置文件缺失时的 fallback）
_HARDCODED_MATRIX: Dict[RegimeState, Dict[str, float]] = {
    RegimeState.BULL: {
        "quality": 1.0,
        "valuation": 0.9,
        "momentum": 1.3,
        "liquidity": 1.0,
        "volatility": 1.0,
        "dividend": 1.0,
        "chip": 0.8,  # 牛市筹码降权（趋势驱动，筹码次要）
        "event": 1.0,
        "analyst": 1.0,
    },
    RegimeState.BEAR: {
        "quality": 1.2,
        "valuation": 1.0,
        "momentum": 0.7,
        "liquidity": 1.0,
        "volatility": 1.2,
        "dividend": 1.0,
        "chip": 1.4,  # 熊市筹码加权（看主力动向更重要）
        "event": 1.0,
        "analyst": 1.0,
    },
    RegimeState.RANGE: {
        "quality": 1.1,
        "valuation": 1.1,
        "momentum": 0.8,
        "liquidity": 1.0,
        "volatility": 1.0,
        "dividend": 1.0,
        "chip": 1.0,  # 震荡正常权重
        "event": 1.0,
        "analyst": 1.0,
    },
    RegimeState.RANGE_LOW_VOL: {
        "quality": 1.1,
        "valuation": 1.1,
        "momentum": 1.0,  # 低波维持动量暴露
        "liquidity": 1.0,
        "volatility": 0.9,
        "dividend": 1.0,
        "chip": 1.0,
        "event": 1.0,
        "analyst": 1.0,
    },
    RegimeState.RANGE_CHOPPY: {
        "quality": 1.2,  # 高波震荡偏防御
        "valuation": 1.1,
        "momentum": 0.6,  # 高波震荡动量降权
        "liquidity": 1.0,
        "volatility": 1.1,
        "dividend": 1.0,
        "chip": 1.0,
        "event": 1.0,
        "analyst": 1.0,
    },
    RegimeState.PANIC: {
        "quality": 1.3,
        "valuation": 1.0,
        "momentum": 0.5,
        "liquidity": 1.2,
        "volatility": 1.3,
        "dividend": 1.1,
        "chip": 1.6,  # 冰点筹码极度加权（恐慌中看主力动向）
        "event": 1.0,
        "analyst": 1.0,
    },
}

# 硬编码策略混合规则（配置缺失时 fallback）
_HARDCODED_BLEND: Dict[RegimeState, Dict[str, float]] = {
    RegimeState.BEAR: {"balanced": 0.7, "defensive": 0.3},
    RegimeState.PANIC: {"balanced": 0.5, "defensive": 0.5},
}

# 惰性加载缓存（配置文件 mtime 变化时自动失效）
_config_cache: dict = {}
_config_mtime: float = 0.0


def _load_config() -> dict:
    """惰性加载 regime_weight_map.yaml，带 mtime 感知缓存。

    配置文件不存在或格式错误时返回空 dict，由调用方回退硬编码。
    """
    global _config_cache, _config_mtime
    from pathlib import Path

    config_path = (
        Path(__file__).resolve().parent.parent.parent
        / "config"
        / "regime_weight_map.yaml"
    )
    if not config_path.exists():
        return {}

    try:
        mtime = config_path.stat().st_mtime
        if _config_cache and mtime == _config_mtime:
            return _config_cache

        from config.loader import ConfigLoader

        _config_cache = ConfigLoader.load("regime_weight_map.yaml") or {}
        _config_mtime = mtime
        return _config_cache
    except Exception as e:
        logger.debug("regime_weight_map.yaml 加载失败: %s", e)
        return {}


# (#7) 向后兼容：OVERLAY_MATRIX 保持为模块级属性，但值来自配置（或 fallback）
# 测试中 `OVERLAY_MATRIX[state]` 仍可访问
OVERLAY_MATRIX = _HARDCODED_MATRIX


def get_overlay_matrix() -> Dict[RegimeState, Dict[str, float]]:
    """获取当前 overlay 矩阵（配置优先，回退硬编码）。

    每次调用都检查配置是否更新（mtime 感知），适合动态调优场景。
    """
    config = _load_config()
    if not config:
        return _HARDCODED_MATRIX

    matrix = {}
    for state in RegimeState:
        state_key = state.name  # "BULL" / "BEAR" / ...
        cfg_mults = config.get(state_key)
        if isinstance(cfg_mults, dict):
            # 确保所有因子都有值，缺失的从硬编码补
            merged = dict(_HARDCODED_MATRIX.get(state, {}))
            merged.update({k: float(v) for k, v in cfg_mults.items()})
            matrix[state] = merged
        else:
            matrix[state] = dict(_HARDCODED_MATRIX.get(state, {}))
    return matrix


def get_strategy_blend() -> Dict[RegimeState, Dict[str, float]]:
    """获取策略混合规则（配置优先，回退硬编码）。"""
    config = _load_config()
    cfg_blend = config.get("strategy_blend")
    if not isinstance(cfg_blend, dict):
        return dict(_HARDCODED_BLEND)

    blend = {}
    for state in RegimeState:
        state_key = state.name
        cfg = cfg_blend.get(state_key)
        if isinstance(cfg, dict):
            blend[state] = {k: float(v) for k, v in cfg.items()}
    # 合并硬编码默认（配置未覆盖的状态仍用默认）
    for state, rules in _HARDCODED_BLEND.items():
        if state not in blend:
            blend[state] = dict(rules)
    return blend


def compute_overlay_weights(
    original_weights: Dict[str, float],
    regime: RegimeState,
    extreme_drop: bool = False,
    national_team: bool = False,
    ic_multipliers: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """对原策略权重施加市场状态 overlay，返回归一化后的新权重。

    v2.x (#7)：
    1. 读取配置中的 multiplier 矩阵（缺失回退硬编码）
    2. 若配置含 strategy_blend 规则，先混合策略权重再施加 overlay
       例如 BEAR 时 balanced:0.7 + defensive:0.3 -> 混合后再乘 multiplier

    v2.8 新增 extreme_drop：极端跌幅时 momentum 强制 ×0.3
    v2.9 新增 national_team：国家队 ETF 放量时 chip multiplier 至少 0.6
    v3.0 新增 ic_multipliers：因子 IC 动态调整 multiplier（IC<0 衰减，floor 0.5）

    三个 v2.8+ 参数的叠加顺序：基础矩阵 → extreme_drop → national_team →
    ic_multipliers。IC floor (0.5) 高于 extreme_drop (0.3)，故 IC 转换可
    拉高 extreme_drop 的过度降权。

    Args:
        original_weights: 策略原权重 dict（含 quality/valuation/momentum/... ）
        regime: 市场状态枚举
        extreme_drop: v2.8 是否触发极端跌幅降动量
        national_team: v2.9 是否触发国家队放量 chip 保底
        ic_multipliers: v3.0 {factor: ic_value} dict，IC ∈ [-1, 1]

    Returns:
        调节并归一化后的新权重 dict（和 = 1.0）
    """
    matrix = get_overlay_matrix()
    blend_rules = get_strategy_blend()

    # (#7) 策略混合：若当前 regime 有混合规则，且 original_weights 含 label（可判断策略名）
    # 则尝试混合。混合仅在策略名匹配 blend 规则时生效。
    weights = dict(original_weights)
    blend_rule = blend_rules.get(regime)
    if blend_rule and "label" in original_weights:
        strategy_name = original_weights.get("label", "")
        if strategy_name in blend_rule:
            # 当前策略在混合规则中，按比例混合
            weights = _blend_strategy_weights(strategy_name, blend_rule, regime)

    # 应用基础矩阵 multiplier
    multipliers = dict(matrix.get(regime, {}))

    # v2.8: extreme_drop 时 momentum 强制 ×0.3
    if extreme_drop and "momentum" in multipliers:
        multipliers["momentum"] = multipliers["momentum"] * 0.3

    # v2.9: national_team 时 chip multiplier 保底 0.6
    if national_team and "chip" in multipliers:
        multipliers["chip"] = max(multipliers["chip"], 0.6)

    # v3.0: IC 动态 multiplier（覆盖式，floor 0.5）
    if ic_multipliers:
        from strategies.factor.ic import ic_to_multiplier

        for factor, ic_val in ic_multipliers.items():
            if factor not in multipliers:
                continue
            base_mult = multipliers[factor]
            multipliers[factor] = ic_to_multiplier(ic_val, base_mult, min_mult=0.5)

    adjusted = {}
    for k, v in weights.items():
        if k in ("label", "two_stage"):
            continue
        mult = multipliers.get(k, 1.0)
        adjusted[k] = v * mult

    total = sum(adjusted.values())
    if total <= 0:
        return original_weights

    # 先归一化保证总和精确为 1.0，再 round 到 4 位
    normalized = {k: v / total for k, v in adjusted.items()}
    return {k: round(v, 4) for k, v in normalized.items()}


def _blend_strategy_weights(
    current_strategy: str,
    blend_rule: Dict[str, float],
    regime: RegimeState,
) -> Dict[str, float]:
    """(#7) 按比例混合当前策略与防御策略的权重。

    Args:
        current_strategy: 当前策略名（如 "balanced"）
        blend_rule: {strategy_name: ratio} 如 {"balanced": 0.7, "defensive": 0.3}
        regime: 市场状态

    Returns:
        混合后的权重 dict（未归一化，由调用方归一化）
    """
    from strategies import get_strategy

    blended = {}
    all_keys = set()
    # 收集所有策略的因子键
    strategy_weights = {}
    for sname in blend_rule:
        sw = get_strategy(sname)
        if sw:
            strategy_weights[sname] = sw
            all_keys.update(sw.keys())

    if not strategy_weights:
        return get_strategy(current_strategy) or {}

    for key in all_keys:
        if key in ("label", "two_stage"):
            continue
        total = 0.0
        for sname, ratio in blend_rule.items():
            sw = strategy_weights.get(sname, {})
            total += sw.get(key, 0) * ratio
        blended[key] = total

    return blended
