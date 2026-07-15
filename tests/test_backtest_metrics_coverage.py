"""backtest/metrics.py 覆盖测试。

mock simulate_strategy 避免网络请求，测试 run_backtest 的指标计算分支、
_fetch_benchmark_returns、_calc_win_by_position。
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import backtest.metrics as metrics_mod
from backtest.metrics import (
    _calc_win_by_position,
    _fetch_benchmark_returns,
    run_backtest,
)


class TestCalcWinByPosition:
    def test_empty_round_results(self):
        assert _calc_win_by_position([], 5) == {}

    def test_zero_holding_days(self):
        assert _calc_win_by_position([{"daily_returns": [0.01]}], 0) == {}

    def test_basic_distribution(self):
        """持仓 6 天，early/mid/late 各 2 天。"""
        round_results = [{"daily_returns": [0.01, -0.01, 0.02, 0.03, -0.02, 0.01]}]
        result = _calc_win_by_position(round_results, 6)
        # thirds = max(1, 6//3) = 2
        # i=0,1 -> early; i=2,3 -> mid; i=4,5 -> late
        assert "early" in result
        assert "mid" in result
        assert "late" in result
        # early: 1 win / 2 total = 50.0
        assert result["early"] == 50.0
        # mid: 2 win / 2 = 100.0
        assert result["mid"] == 100.0
        # late: 1 win / 2 = 50.0
        assert result["late"] == 50.0

    def test_small_holding_days_thirds_min_one(self):
        """holding_days < 3 时 thirds=1。"""
        round_results = [{"daily_returns": [0.01, -0.01, 0.02]}]
        result = _calc_win_by_position(round_results, 2)
        # thirds = max(1, 2//3) = max(1, 0) = 1
        # i=0 -> early; i=1,2 -> late (i < 1*2=2 ? mid : late)
        assert "early" in result

    def test_zero_total_position(self):
        """total=0 的位置返回 0。"""
        round_results = [{"daily_returns": []}]
        result = _calc_win_by_position(round_results, 5)
        assert all(v == 0 for v in result.values())


class TestFetchBenchmarkReturns:
    def test_empty_code_returns_none(self):
        assert _fetch_benchmark_returns("", 60) is None

    def test_exception_returns_none(self):
        with patch("data.get_kline", side_effect=Exception("net")):
            assert _fetch_benchmark_returns("sh000300", 60) is None

    def test_insufficient_bars_returns_none(self):
        """K 线不足 2 根返回 None。"""

        class _Bar:
            def __init__(self, close):
                self.close = close

        with patch("data.get_kline", return_value=[_Bar(10.0)]):
            assert _fetch_benchmark_returns("sh000300", 60) is None

    def test_valid_returns_computed(self):
        class _Bar:
            def __init__(self, close):
                self.close = close

        bars = [_Bar(10.0), _Bar(11.0), _Bar(10.45)]
        with patch("data.get_kline", return_value=bars):
            result = _fetch_benchmark_returns("sh000300", 60)
        # (11-10)/10=0.1, (10.45-11)/11≈-0.05
        assert len(result) == 2
        assert result[0] == pytest.approx(0.1)
        assert result[1] == pytest.approx(-0.05, abs=1e-6)


class TestRunBacktest:
    def test_error_propagated(self):
        """simulate_strategy 返回 error 时透传。"""
        with patch.object(
            metrics_mod, "simulate_strategy", return_value={"error": "no data"}
        ):
            result = run_backtest("balanced", ["sh600519"], days=60)
        assert result == {"error": "no data"}

    def test_no_periods_returns_error(self):
        with patch.object(
            metrics_mod,
            "simulate_strategy",
            return_value={"returns": [], "daily_returns": []},
        ):
            result = run_backtest("balanced", ["sh600519"], days=60)
        assert result == {"error": "回测失败，无有效数据"}

    def test_basic_metrics_calculation(self):
        """测试正常的指标计算路径（无 benchmark）。"""
        fake_result = {
            "returns": [5.0, -2.0, 3.0],  # 三期收益
            "daily_returns": [0.01, -0.005, 0.02, 0.005, -0.01] * 4,
        }
        with patch.object(metrics_mod, "simulate_strategy", return_value=fake_result):
            result = run_backtest("balanced", ["sh600519"], days=60, rounds=3)
        assert result["strategy"] == "balanced"
        assert result["rounds"] == 3
        # 累计收益 = ((1.05*0.98*1.03)-1)*100
        expected_total = ((1.05 * 0.98 * 1.03) - 1) * 100
        assert abs(result["total_return_pct"] - round(expected_total, 2)) < 0.01
        assert result["win_rate_pct"] == round(2 / 3 * 100, 1)
        assert result["benchmark"] == "none"
        assert "win_by_position" in result
        assert "round_details" in result

    def test_metrics_with_benchmark_no_ir(self):
        """有 benchmark 但 benchmark_returns 不足时不计算 IR。"""
        fake_result = {
            "returns": [5.0, -2.0],
            "daily_returns": [0.01, -0.005, 0.02, 0.005] * 2,
        }
        with (
            patch.object(metrics_mod, "simulate_strategy", return_value=fake_result),
            patch.object(metrics_mod, "_fetch_benchmark_returns", return_value=[0.001]),
        ):
            result = run_backtest(
                "balanced", ["sh600519"], days=60, benchmark="sh000300"
            )
        # benchmark_returns 长度 1 < 2 -> IR=0
        assert result["information_ratio"] == 0
        assert result["benchmark"] == "sh000300"

    def test_metrics_with_benchmark_ir_computed(self):
        """benchmark 足够长时计算信息比率。"""
        fake_result = {
            "returns": [5.0, -2.0, 3.0, 1.0],
            "daily_returns": [0.01, -0.005, 0.02, 0.005, -0.01] * 5,
        }
        # benchmark 60 天日收益
        bench = [0.001] * 60
        with (
            patch.object(metrics_mod, "simulate_strategy", return_value=fake_result),
            patch.object(metrics_mod, "_fetch_benchmark_returns", return_value=bench),
        ):
            result = run_backtest(
                "balanced", ["sh600519"], days=60, rounds=4, benchmark="sh000300"
            )
        assert result["benchmark"] == "sh000300"
        assert isinstance(result["information_ratio"], (int, float))

    def test_all_negative_returns(self):
        """全部亏损时盈亏比为 0（无亏损）... 实际 avg_loss>0。"""
        fake_result = {
            "returns": [-5.0, -2.0, -3.0],
            "daily_returns": [-0.01, -0.005, -0.02, -0.005, -0.01] * 3,
        }
        with patch.object(metrics_mod, "simulate_strategy", return_value=fake_result):
            result = run_backtest("balanced", ["sh600519"], days=60, rounds=3)
        assert result["win_rate_pct"] == 0.0
        assert result["profit_loss_ratio"] == 0  # avg_win=0 -> 0

    def test_no_daily_returns_uses_period_fallback(self):
        """无 daily_returns 时回退到 all_returns 计算最大回撤。"""
        fake_result = {
            "returns": [5.0, -10.0, 3.0],
            "daily_returns": [],
        }
        with patch.object(metrics_mod, "simulate_strategy", return_value=fake_result):
            result = run_backtest("balanced", ["sh600519"], days=60, rounds=3)
        # sharpe=0 (无 daily_returns), max_drawdown 基于期收益
        assert result["sharpe_ratio"] == 0
        assert result["max_drawdown_pct"] >= 0
