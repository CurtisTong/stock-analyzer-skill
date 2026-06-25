"""
策略模式识别模块

包含：
- 三阴一阳战法（patterns_local.py）
- MA + 成交量组合策略（ma_volume_strategy.py）
"""

from .ma_volume_strategy import (
    detect_ma_volume_signal,
    backtest_strategy,
    get_strategy_params,
)

__all__ = ["detect_ma_volume_signal", "backtest_strategy", "get_strategy_params"]
