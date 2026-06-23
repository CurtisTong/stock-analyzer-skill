"""
策略引擎层：因子注册、策略配置、评分管道。
"""

from .registry import (
    STRATEGIES,
    get_strategy,
    register_strategy,
    list_strategies,
)
from .factors import (
    quality_score,
    valuation_score,
    momentum_score,
    liquidity_score,
    dividend_score,
    chip_score_static,
    chip_score_dynamic,
    chip_details,
)
from .factors.volatility import volatility_from_closes
