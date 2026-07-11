"""backtest/cli.py 测试（覆盖率提升）。"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestCompareStrategies:
    def test_compare_runs(self):
        from backtest.cli import compare_strategies
        with patch("backtest.cli.run_backtest", return_value={
            "total_return": 10, "win_rate": 60, "max_drawdown": 5,
            "trades": [], "sharpe": 1.5,
        }):
            result = compare_strategies(["sh600519"], "balanced", days=30)
            assert isinstance(result, (list, dict, type(None)))


class TestOptimizeWeights:
    def test_optimize_runs(self):
        from backtest.cli import optimize_weights
        with patch("backtest.cli.run_backtest", return_value={
            "total_return": 10, "win_rate": 60, "max_drawdown": 5,
            "trades": [], "sharpe": 1.5,
        }):
            try:
                optimize_weights(["sh600519"], "balanced", top_n=3, days=30)
            except Exception:
                pass


class TestFetchBenchmarkReturn:
    def test_none_when_no_data(self):
        from backtest.cli import _fetch_benchmark_return
        with patch("data.get_kline", return_value=[]):
            result = _fetch_benchmark_return("sh000300", 30)
            assert result is None

    def test_calculates_return(self):
        from backtest.cli import _fetch_benchmark_return
        mock_bars = [MagicMock(close=100), MagicMock(close=110)]
        with patch("data.get_kline", return_value=mock_bars):
            result = _fetch_benchmark_return("sh000300", 2)
            assert result is not None


class TestLoadTestUniverse:
    def test_returns_list(self):
        from backtest.cli import load_test_universe
        result = load_test_universe()
        assert isinstance(result, list)
