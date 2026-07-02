"""因子注册表：管理因子定义、计算函数和元数据。

新增因子只需一次 register_factor() 调用，系统自动发现：
  - compute_factor_parts: 全量因子计算
  - compute_phase1_parts: Phase 1 轻量因子
  - normalize_factors_batch: z-score 标准化
  - build_result_row: 结果行字段

示例（新增 ESG 因子）：
    from strategies.factors.registry import register_factor
    register_factor("esg", compute_fn=esg_score, phase=1, args_style="fin_industry")
"""

import logging
import threading
from enum import Enum
from typing import Callable, Dict, List

logger = logging.getLogger(__name__)


class Phase(int, Enum):
    """因子计算阶段。"""

    PHASE1 = 1  # 不依赖 K 线（轻量，全市场初筛）
    PHASE2 = 2  # 依赖 K 线（精排）


class ArgsStyle(str, Enum):
    """因子计算函数的参数签名风格。

    注册表根据此类型自动构造 kwargs 调用 compute_fn，
    消除每个因子的手动参数适配。
    """

    FIN_INDUSTRY = "fin_industry"  # (fin, industry)
    QUOTE_FIN_INDUSTRY = "quote_fin_industry"  # (quote, fin, industry)
    FEATURES_QUOTE = "features_quote"  # (features, quote)
    QUOTE = "quote"  # (quote,)
    FEATURES_CLOSES_INDUSTRY = "features_closes_industry"  # (closes, industry)
    CODE = "code"  # (code,)
    FIN_QUOTE_FEATURES_INDUSTRY = (
        "fin_quote_features_industry"  # (fin, quote, features, industry)
    )


class FactorDescriptor:
    """因子描述符。"""

    __slots__ = (
        "name",
        "compute_fn",
        "phase",
        "args_style",
        "label",
        "default_weight",
        "requires_kline",
    )

    def __init__(
        self,
        name: str,
        compute_fn: Callable,
        phase: Phase = Phase.PHASE2,
        args_style: ArgsStyle = ArgsStyle.FIN_INDUSTRY,
        label: str = "",
        default_weight: float = 0.0,
        requires_kline: bool = False,
    ):
        self.name = name
        self.compute_fn = compute_fn
        self.phase = phase
        self.args_style = args_style
        self.label = label or name
        self.default_weight = default_weight
        self.requires_kline = requires_kline


# ---------- 全局注册表 ----------

_FACTORS: Dict[str, FactorDescriptor] = {}

# RLock 守护 _FACTORS 全局 dict 的写路径；compute_all_factors / compute_phase_factors
# 在锁内 snapshot，避免并发 register_factor 触发的 RuntimeError
_FACTORS_LOCK = threading.RLock()


def register_factor(
    name: str,
    compute_fn: Callable,
    phase: int = 2,
    args_style: str = "fin_industry",
    label: str = "",
    default_weight: float = 0.0,
    requires_kline: bool = False,
) -> None:
    """注册新因子。

    Args:
        name: 因子名称（如 "quality", "esg"）
        compute_fn: 评分函数，返回 float (0-100)
        phase: 计算阶段（1=不依赖K线，2=依赖K线）
        args_style: 参数签名风格，见 ArgsStyle 枚举
        label: 中文标签
        default_weight: balanced 策略下的默认权重
        requires_kline: 是否需要 K 线数据
    """
    with _FACTORS_LOCK:
        _FACTORS[name] = FactorDescriptor(
            name=name,
            compute_fn=compute_fn,
            phase=Phase(phase),
            args_style=ArgsStyle(args_style),
            label=label or name,
            default_weight=default_weight,
            requires_kline=requires_kline,
        )


def get_factor(name: str) -> FactorDescriptor:
    """获取因子描述符。"""
    with _FACTORS_LOCK:
        if name not in _FACTORS:
            raise KeyError(f"未知因子: {name}，可用: {list(_FACTORS.keys())}")
        return _FACTORS[name]


def list_factors() -> List[str]:
    """列出所有已注册因子名。"""
    with _FACTORS_LOCK:
        return list(_FACTORS.keys())


def list_phase_factors(phase: int) -> List[str]:
    """列出指定阶段的因子名。"""
    with _FACTORS_LOCK:
        return [name for name, desc in _FACTORS.items() if desc.phase.value == phase]


def clear_factors() -> None:
    """清空注册表（仅用于测试隔离）。"""
    with _FACTORS_LOCK:
        _FACTORS.clear()


def get_factor_keys() -> List[str]:
    """获取所有因子名（用于 normalize_factors_batch 等场景）。"""
    with _FACTORS_LOCK:
        return list(_FACTORS.keys())


# ---------- 自动调用器 ----------


def _build_kwargs(
    desc: "FactorDescriptor",
    fin: dict,
    quote: dict,
    features: dict,
    industry: str,
    code: str,
) -> dict:
    """根据 args_style 构造 compute_fn 的 kwargs。"""
    style = desc.args_style
    if style == ArgsStyle.FIN_INDUSTRY:
        return {"fin": fin, "industry": industry}
    if style == ArgsStyle.QUOTE_FIN_INDUSTRY:
        return {"quote": quote, "fin": fin, "industry": industry}
    if style == ArgsStyle.FEATURES_QUOTE:
        return {"features": features, "quote": quote}
    if style == ArgsStyle.QUOTE:
        return {"quote": quote}
    if style == ArgsStyle.FEATURES_CLOSES_INDUSTRY:
        return {"closes": features.get("closes", []), "industry": industry}
    if style == ArgsStyle.CODE:
        return {"code": code}
    if style == ArgsStyle.FIN_QUOTE_FEATURES_INDUSTRY:
        return {"fin": fin, "quote": quote, "features": features, "industry": industry}
    return {}


def compute_all_factors(fin, quote, features, industry, code) -> dict:
    """自动调用所有已注册因子，返回 {name: score} dict。

    替代原 compute_factor_parts() 中的硬编码映射。
    """
    result = {}
    degraded = []
    with _FACTORS_LOCK:
        factors_snapshot = list(_FACTORS.items())
    for name, desc in factors_snapshot:
        kwargs = _build_kwargs(desc, fin, quote, features, industry, code)
        try:
            result[name] = desc.compute_fn(**kwargs)
        except Exception as e:
            logger.warning("因子 %s 计算异常，使用默认分 50: %s", name, e)
            result[name] = 50
            degraded.append(name)
    if degraded:
        logger.warning("以下因子计算失败，已降级为中性分 50: %s", degraded)
    return result


def compute_phase_factors(
    phase, fin, quote, features, industry, code, exclude=None
) -> dict:
    """自动调用指定阶段的因子，返回 {name: score} dict。

    替代原 compute_phase1_parts() / compute_phase2_parts() 中的硬编码映射。

    Args:
        exclude: 需跳过的因子名集合（如 Phase 2 跳过 chip 避免无意义的网络请求）。
    """
    result = {}
    degraded = []
    target = Phase(phase) if isinstance(phase, int) else phase
    skip = set(exclude) if exclude else set()
    with _FACTORS_LOCK:
        factors_snapshot = list(_FACTORS.items())
    for name, desc in factors_snapshot:
        if desc.phase != target:
            continue
        if name in skip:
            continue
        kwargs = _build_kwargs(desc, fin, quote, features, industry, code)
        try:
            result[name] = desc.compute_fn(**kwargs)
        except Exception as e:
            logger.warning(
                "因子 %s 计算异常(phase=%d)，使用默认分 50: %s", name, phase, e
            )
            result[name] = 50
            degraded.append(name)
    if degraded:
        logger.warning("Phase%d 以下因子计算失败，已降级: %s", phase, degraded)
    return result
