"""
策略引擎层：因子注册、策略配置、评分管道。
"""

from .registry import (
    STRATEGIES,
    STRATEGY_VALIDATION,
    get_strategy,
    get_validation,
    register_strategy,
    list_strategies,
    strategy_exists,
)
from .oos_validation import (
    OOS_FILE,
    OOS_MIN_STOCKS,
    OOS_MIN_WIN_RATE,
    build_oos_note,
    evaluate_oos,
    load_oos_overrides,
    save_oos_result,
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
