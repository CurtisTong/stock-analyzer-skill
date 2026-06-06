"""
backtest.py 单元测试：覆盖回测框架核心逻辑。
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from common import to_float


class TestFetchHistoricalReturns:
    """历史收益率序列计算。"""

    def test_empty_records_returns_empty(self, monkeypatch):
        import backtest
        monkeypatch.setattr(backtest, "fetch_kline", lambda code, limit, scale: [])
        result = backtest.fetch_historical_returns("sh600519", 60)
        assert result == []

    def test_single_record_returns_empty(self, monkeypatch):
        import backtest
        monkeypatch.setattr(backtest, "fetch_kline", lambda code, limit, scale: [
            {"close": "100.0"}
        ])
        result = backtest.fetch_historical_returns("sh600519", 60)
        assert result == []

    def test_calculates_returns_correctly(self, monkeypatch):
        import backtest
        kline = [
            {"close": "100.0"},
            {"close": "110.0"},  # +10%
            {"close": "99.0"},   # -10%
            {"close": "108.9"},  # +10%
        ]
        monkeypatch.setattr(backtest, "fetch_kline", lambda code, limit, scale: kline)
        result = backtest.fetch_historical_returns("sh600519", 60)
        assert len(result) == 3
        assert result[0] == pytest.approx(0.1)    # +10%
        assert result[1] == pytest.approx(-0.1)   # -10%
        assert result[2] == pytest.approx(0.1)    # +10%

    def test_zero_prev_close_skipped(self, monkeypatch):
        import backtest
        kline = [
            {"close": "0"},
            {"close": "100.0"},
            {"close": "110.0"},
        ]
        monkeypatch.setattr(backtest, "fetch_kline", lambda code, limit, scale: kline)
        result = backtest.fetch_historical_returns("sh600519", 60)
        # 第一对 prev_close=0 应跳过
        assert len(result) == 1
        assert result[0] == pytest.approx(0.1)


class TestSimulateStrategy:
    """策略模拟测试。"""

    def _mock_dependencies(self, monkeypatch, sample_quote, sample_finance, kline_uptrend):
        """统一 mock 外部依赖。"""
        import backtest
        import quote
        import screener

        monkeypatch.setattr(quote, "fetch_batch", lambda codes: [sample_quote] * len(codes))
        monkeypatch.setattr(backtest, "fetch_finance", lambda code: [sample_finance])
        monkeypatch.setattr(backtest, "fetch_kline", lambda code, limit, scale: kline_uptrend)
        monkeypatch.setattr(screener, "fetch_kline", lambda code, limit, scale: kline_uptrend)
        monkeypatch.setattr(screener, "fetch_finance", lambda code: [sample_finance])

    def test_returns_all_fields(self, monkeypatch, sample_quote, sample_finance, kline_uptrend):
        import backtest
        self._mock_dependencies(monkeypatch, sample_quote, sample_finance, kline_uptrend)

        result = backtest.simulate_strategy("balanced", ["sh600519"], top_n=1, holding_days=5)
        assert "strategy" in result
        assert "selected" in result
        assert "returns" in result
        assert "avg_return_pct" in result
        assert result["strategy"] == "balanced"

    def test_empty_quotes_returns_error(self, monkeypatch):
        import backtest
        import quote
        monkeypatch.setattr(quote, "fetch_batch", lambda codes: [])
        result = backtest.simulate_strategy("balanced", ["sh600519"])
        assert "error" in result

    def test_selected_count_matches_top_n(self, monkeypatch, sample_quote, sample_finance, kline_uptrend):
        import backtest
        import quote
        import screener

        # 返回多只股票
        quotes = [{**sample_quote, "code": f"60000{i}"} for i in range(5)]
        monkeypatch.setattr(quote, "fetch_batch", lambda codes: quotes)
        monkeypatch.setattr(backtest, "fetch_finance", lambda code: [sample_finance])
        monkeypatch.setattr(backtest, "fetch_kline", lambda code, limit, scale: kline_uptrend)
        monkeypatch.setattr(screener, "fetch_kline", lambda code, limit, scale: kline_uptrend)
        monkeypatch.setattr(screener, "fetch_finance", lambda code: [sample_finance])

        result = backtest.simulate_strategy("balanced", [f"60000{i}" for i in range(5)], top_n=3)
        assert len(result["selected"]) == 3

    def test_finance_data_fetched(self, monkeypatch, sample_quote, sample_finance, kline_uptrend):
        """验证回测时实际拉取财务数据（修复 P0: fin={} 问题）。"""
        import backtest
        import quote
        import screener

        finance_called = {"count": 0}

        def mock_fetch_finance(code):
            finance_called["count"] += 1
            return [sample_finance]

        monkeypatch.setattr(quote, "fetch_batch", lambda codes: [sample_quote])
        monkeypatch.setattr(backtest, "fetch_finance", mock_fetch_finance)
        monkeypatch.setattr(backtest, "fetch_kline", lambda code, limit, scale: kline_uptrend)
        monkeypatch.setattr(screener, "fetch_kline", lambda code, limit, scale: kline_uptrend)
        monkeypatch.setattr(screener, "fetch_finance", mock_fetch_finance)

        backtest.simulate_strategy("balanced", ["sh600519"], top_n=1, holding_days=5)
        assert finance_called["count"] > 0


class TestRunBacktest:
    """多轮回测测试。"""

    def test_returns_statistical_fields(self, monkeypatch, sample_quote, sample_finance, kline_uptrend):
        import backtest
        import quote
        import screener

        monkeypatch.setattr(quote, "fetch_batch", lambda codes: [sample_quote] * len(codes))
        monkeypatch.setattr(backtest, "fetch_finance", lambda code: [sample_finance])
        monkeypatch.setattr(backtest, "fetch_kline", lambda code, limit, scale: kline_uptrend)
        monkeypatch.setattr(screener, "fetch_kline", lambda code, limit, scale: kline_uptrend)
        monkeypatch.setattr(screener, "fetch_finance", lambda code: [sample_finance])

        result = backtest.run_backtest("balanced", ["sh600519"], top_n=1, days=30, rounds=3)
        assert "total_return_pct" in result
        assert "avg_return_pct" in result
        assert "win_rate_pct" in result
        assert "sharpe_ratio" in result
        assert "max_drawdown_pct" in result
        assert "round_details" in result

    def test_win_rate_between_0_and_100(self, monkeypatch, sample_quote, sample_finance, kline_uptrend):
        import backtest
        import quote
        import screener

        monkeypatch.setattr(quote, "fetch_batch", lambda codes: [sample_quote] * len(codes))
        monkeypatch.setattr(backtest, "fetch_finance", lambda code: [sample_finance])
        monkeypatch.setattr(backtest, "fetch_kline", lambda code, limit, scale: kline_uptrend)
        monkeypatch.setattr(screener, "fetch_kline", lambda code, limit, scale: kline_uptrend)
        monkeypatch.setattr(screener, "fetch_finance", lambda code: [sample_finance])

        result = backtest.run_backtest("balanced", ["sh600519"], top_n=1, days=30, rounds=3)
        assert 0 <= result["win_rate_pct"] <= 100


class TestOptimizeWeights:
    """权重优化测试。"""

    def test_restores_original_weights(self, monkeypatch, sample_quote, sample_finance, kline_uptrend):
        """验证优化后原始权重被恢复（修复 P0: 全局修改问题）。"""
        import backtest
        import quote
        import screener

        monkeypatch.setattr(quote, "fetch_batch", lambda codes: [sample_quote] * len(codes))
        monkeypatch.setattr(backtest, "fetch_finance", lambda code: [sample_finance])
        monkeypatch.setattr(backtest, "fetch_kline", lambda code, limit, scale: kline_uptrend)
        monkeypatch.setattr(screener, "fetch_kline", lambda code, limit, scale: kline_uptrend)
        monkeypatch.setattr(screener, "fetch_finance", lambda code: [sample_finance])

        original = {k: v for k, v in screener.STRATEGIES["balanced"].items()}
        backtest.optimize_weights(["sh600519"], "balanced", top_n=1, days=10)
        assert screener.STRATEGIES["balanced"] == original

    def test_restores_weights_on_exception(self, monkeypatch, sample_quote, sample_finance, kline_uptrend):
        """验证异常时也能恢复权重。"""
        import backtest
        import quote
        import screener

        monkeypatch.setattr(quote, "fetch_batch", lambda codes: [sample_quote] * len(codes))
        monkeypatch.setattr(backtest, "fetch_finance", lambda code: [sample_finance])
        monkeypatch.setattr(backtest, "fetch_kline", lambda code, limit, scale: kline_uptrend)
        monkeypatch.setattr(screener, "fetch_kline", lambda code, limit, scale: kline_uptrend)
        monkeypatch.setattr(screener, "fetch_finance", lambda code: [sample_finance])

        original = {k: v for k, v in screener.STRATEGIES["balanced"].items()}

        # 让 run_backtest 在第二次调用时抛异常
        call_count = {"n": 0}
        original_run_backtest = backtest.run_backtest

        def failing_run_backtest(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] > 3:
                raise RuntimeError("模拟异常")
            return original_run_backtest(*args, **kwargs)

        monkeypatch.setattr(backtest, "run_backtest", failing_run_backtest)

        with pytest.raises(RuntimeError):
            backtest.optimize_weights(["sh600519"], "balanced", top_n=1, days=10)

        assert screener.STRATEGIES["balanced"] == original

    def test_returns_best_weights(self, monkeypatch, sample_quote, sample_finance, kline_uptrend):
        import backtest
        import quote
        import screener

        monkeypatch.setattr(quote, "fetch_batch", lambda codes: [sample_quote] * len(codes))
        monkeypatch.setattr(backtest, "fetch_finance", lambda code: [sample_finance])
        monkeypatch.setattr(backtest, "fetch_kline", lambda code, limit, scale: kline_uptrend)
        monkeypatch.setattr(screener, "fetch_kline", lambda code, limit, scale: kline_uptrend)
        monkeypatch.setattr(screener, "fetch_finance", lambda code: [sample_finance])

        result = backtest.optimize_weights(["sh600519"], "balanced", top_n=1, days=10)
        assert "best_weights" in result
        assert "best_sharpe" in result
        assert "baseline_sharpe" in result
        assert "improvement" in result
        assert "all_results" in result


class TestCompareStrategies:
    """策略比较测试。"""

    def test_compares_all_strategies(self, monkeypatch, sample_quote, sample_finance, kline_uptrend):
        import backtest
        import quote
        import screener

        monkeypatch.setattr(quote, "fetch_batch", lambda codes: [sample_quote] * len(codes))
        monkeypatch.setattr(backtest, "fetch_finance", lambda code: [sample_finance])
        monkeypatch.setattr(backtest, "fetch_kline", lambda code, limit, scale: kline_uptrend)
        monkeypatch.setattr(screener, "fetch_kline", lambda code, limit, scale: kline_uptrend)
        monkeypatch.setattr(screener, "fetch_finance", lambda code: [sample_finance])

        results = backtest.compare_strategies(["sh600519"], top_n=1, days=10, rounds=2)
        assert len(results) == 5  # 5 种策略
        assert "balanced" in results
        assert "quality_value" in results
        assert "growth_momentum" in results
        assert "defensive" in results
        assert "turning_point" in results
