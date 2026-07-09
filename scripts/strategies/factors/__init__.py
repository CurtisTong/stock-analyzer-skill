"""
因子实现：quality / valuation / momentum / liquidity / volatility / dividend / chip。
自动注册到因子注册表。
"""

from .quality import quality_score
from .valuation import valuation_score
from .momentum import momentum_score
from .liquidity import liquidity_score
from .volatility import volatility_score, volatility_from_closes
from .dividend import dividend_score
from .chip import chip_score_static, chip_score_dynamic, chip_details
from .event import event_score
from .analyst import analyst_expectation_score
from .registry import register_factor, get_factor_keys

# ---------- 自动注册内置因子 ----------

register_factor(
    "quality",
    compute_fn=quality_score,
    phase=1,
    args_style="fin_industry",
    label="质量",
    default_weight=0.30,
)

register_factor(
    "valuation",
    compute_fn=valuation_score,
    phase=1,
    args_style="quote_fin_industry",
    label="估值",
    default_weight=0.20,
)

register_factor(
    "momentum",
    compute_fn=momentum_score,
    phase=2,
    args_style="features_quote",
    label="动量",
    default_weight=0.15,
    requires_kline=True,
)

register_factor(
    "liquidity",
    compute_fn=liquidity_score,
    phase=1,
    args_style="quote",
    label="流动性",
    default_weight=0.05,
)

register_factor(
    "volatility",
    compute_fn=volatility_from_closes,
    phase=2,
    args_style="features_closes_industry",
    label="波动率",
    default_weight=0.15,
    requires_kline=True,
)

register_factor(
    "dividend",
    compute_fn=dividend_score,
    phase=2,
    args_style="quote_fin_industry",
    label="红利",
    default_weight=0.05,
)

register_factor(
    "chip",
    compute_fn=chip_score_static,
    phase=2,
    args_style="code",
    label="筹码",
    default_weight=0.10,
)

register_factor(
    "event",
    compute_fn=event_score,
    phase=1,
    args_style="code",
    label="事件",
    # P2-H2: 与 6 策略配置对齐（event 权重均为 0.0），default_weight 改 0.0
    default_weight=0.0,
)

register_factor(
    "analyst",
    compute_fn=analyst_expectation_score,
    phase=1,
    args_style="quote_fin_industry",
    label="分析师",
    default_weight=0.0,
)
