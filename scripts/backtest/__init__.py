"""
多因子选股策略回测框架。

为保持向后兼容，所有公共符号从子模块重导出：
    from backtest import run_backtest, simulate_strategy, compare_strategies, ...
"""

from data import get_kline, get_finance  # 重导出供测试 monkeypatch
from .engine import (
    fetch_historical_returns,
    simulate_strategy,
    _calc_rsi,
    _calc_daily_returns,
    _compute_momentum_from_bars,
    _calc_dividend_score,
    _build_hist_quote,
)
from .metrics import run_backtest, _fetch_benchmark_returns, _calc_win_by_position
from .cli import compare_strategies, optimize_weights, load_test_universe, main

__all__ = [
    "fetch_historical_returns",
    "simulate_strategy",
    "run_backtest",
    "compare_strategies",
    "optimize_weights",
    "load_test_universe",
    "main",
    # 内部函数（测试需要）
    "_calc_rsi",
    "_calc_daily_returns",
    "_compute_momentum_from_bars",
    "_calc_dividend_score",
    "_build_hist_quote",
    "_fetch_benchmark_returns",
    "_calc_win_by_position",
]
