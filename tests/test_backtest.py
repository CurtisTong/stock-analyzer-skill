"""
backtest.py 单元测试：覆盖回测框架核心逻辑。
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from data.types import Quote, KlineBar, FinanceRecord


def _make_quote_obj(code="sh600519", name="贵州茅台", price=1800.0, **kwargs):
    """构造 Quote dataclass。"""
    defaults = dict(code=code, name=name, price=price, pe=25.6, pb=8.2,
                    total_cap=22600, circulating_cap=22600, amount=2234567,
                    turnover=0.15, change_pct=0.56)
    defaults.update(kwargs)
    return Quote(**defaults)


def _make_kline_bars(prices):
    """从价格列表构造 KlineBar 列表。"""
    return [KlineBar(day=f"2025-01-{i+1:02d}", close=p, open=p, high=p, low=p)
            for i, p in enumerate(prices)]


def _make_finance_obj(**kwargs):
    """构造 FinanceRecord dataclass。"""
    defaults = dict(eps=50.0, roe=30.5, revenue_yoy=15.2, net_profit_yoy=18.3,
                    gross_margin=91.5, debt_ratio=18.7, ocf_per_share=55.0)
    defaults.update(kwargs)
    return FinanceRecord(**defaults)


class TestFetchHistoricalReturns:
    """历史收益率序列计算。"""

    def test_empty_records_returns_empty(self, monkeypatch):
        import backtest
        monkeypatch.setattr(backtest, "get_kline", lambda code, scale=240, datalen=65: [])
        result = backtest.fetch_historical_returns("sh600519", 60)
        assert result == []

    def test_single_record_returns_empty(self, monkeypatch):
        import backtest
        bars = _make_kline_bars([100.0])
        monkeypatch.setattr(backtest, "get_kline", lambda code, scale=240, datalen=65: bars)
        result = backtest.fetch_historical_returns("sh600519", 60)
        assert result == []

    def test_calculates_returns_correctly(self, monkeypatch):
        import backtest
        bars = _make_kline_bars([100.0, 110.0, 99.0, 108.9])
        monkeypatch.setattr(backtest, "get_kline", lambda code, scale=240, datalen=65: bars)
        result = backtest.fetch_historical_returns("sh600519", 60)
        assert len(result) == 3
        assert result[0] == pytest.approx(0.1)    # +10%
        assert result[1] == pytest.approx(-0.1)   # -10%
        assert result[2] == pytest.approx(0.1)    # +10%

    def test_zero_prev_close_skipped(self, monkeypatch):
        import backtest
        bars = _make_kline_bars([0.0, 100.0, 110.0])
        monkeypatch.setattr(backtest, "get_kline", lambda code, scale=240, datalen=65: bars)
        result = backtest.fetch_historical_returns("sh600519", 60)
        assert len(result) == 1
        assert result[0] == pytest.approx(0.1)


class TestSimulateStrategy:
    """策略模拟测试。"""

    def _mock_all(self, monkeypatch, sample_finance_dict, kline_uptrend):
        """统一 mock 数据层和 screener 适配器。"""
        import backtest
        import screener

        quote_obj = _make_quote_obj()
        finance_obj = _make_finance_obj()


        monkeypatch.setattr(backtest, "get_finance", lambda code: [finance_obj])
        # 滚动窗口需要至少 60+holding_days 根 K 线
        monkeypatch.setattr(backtest, "get_kline", lambda code, scale=240, datalen=70: _make_kline_bars([10+i*0.3 for i in range(70)]))

    def test_returns_all_fields(self, monkeypatch, sample_finance, kline_uptrend):
        import backtest
        self._mock_all(monkeypatch, sample_finance, kline_uptrend)

        result = backtest.simulate_strategy("balanced", ["sh600519"], top_n=1, holding_days=5)
        assert "strategy" in result
        assert "selections" in result
        assert "returns" in result
        assert "avg_return_pct" in result
        assert "total_periods" in result
        assert result["strategy"] == "balanced"

    def test_no_kline_returns_error(self, monkeypatch):
        """K 线数据不足时返回错误。"""
        import backtest
        monkeypatch.setattr(backtest, "get_kline", lambda code, scale=240, datalen=70: [])
        monkeypatch.setattr(backtest, "get_finance", lambda code: [])

        result = backtest.simulate_strategy("balanced", ["sh600519"])
        assert "error" in result

    def test_rolling_window_generates_returns(self, monkeypatch, sample_finance, kline_uptrend):
        """验证滚动窗口生成多个收益周期。"""
        import backtest
        import screener

        finance_obj = _make_finance_obj()
        quote_obj = _make_quote_obj()

        # 提供足够的 K 线数据（100 根）
        monkeypatch.setattr(backtest, "get_kline", lambda code, scale=240, datalen=100: _make_kline_bars([10+i*0.2 for i in range(100)]))
        monkeypatch.setattr(backtest, "get_finance", lambda code: [finance_obj])


        result = backtest.simulate_strategy("balanced", ["sh600519"], top_n=1, holding_days=10)
        assert "error" not in result
        assert result["total_periods"] > 1  # 滚动窗口应产生多个周期
        assert len(result["returns"]) == result["total_periods"]

    def test_finance_data_fetched(self, monkeypatch, sample_finance, kline_uptrend):
        """验证回测时实际拉取财务数据。"""
        import backtest

        quote_obj = _make_quote_obj()
        finance_obj = _make_finance_obj()
        finance_called = {"count": 0}

        def mock_get_finance(code):
            finance_called["count"] += 1
            return [finance_obj]


        monkeypatch.setattr(backtest, "get_finance", mock_get_finance)
        monkeypatch.setattr(backtest, "get_kline", lambda code, scale=240, datalen=70: _make_kline_bars([10+i*0.3 for i in range(70)]))

        backtest.simulate_strategy("balanced", ["sh600519"], top_n=1, holding_days=5)
        assert finance_called["count"] > 0


class TestRunBacktest:
    """多轮回测测试。"""

    def _mock_all(self, monkeypatch, sample_finance, kline_uptrend):
        import backtest

        quote_obj = _make_quote_obj()
        finance_obj = _make_finance_obj()


        monkeypatch.setattr(backtest, "get_finance", lambda code: [finance_obj])
        monkeypatch.setattr(backtest, "get_kline", lambda code, scale=240, datalen=70: _make_kline_bars([10+i*0.3 for i in range(70)]))

    def test_returns_statistical_fields(self, monkeypatch, sample_finance, kline_uptrend):
        import backtest
        self._mock_all(monkeypatch, sample_finance, kline_uptrend)

        result = backtest.run_backtest("balanced", ["sh600519"], top_n=1, days=30, rounds=3)
        assert "total_return_pct" in result
        assert "avg_return_pct" in result
        assert "win_rate_pct" in result
        assert "sharpe_ratio" in result
        assert "max_drawdown_pct" in result
        assert "round_details" in result

    def test_win_rate_between_0_and_100(self, monkeypatch, sample_finance, kline_uptrend):
        import backtest
        self._mock_all(monkeypatch, sample_finance, kline_uptrend)

        result = backtest.run_backtest("balanced", ["sh600519"], top_n=1, days=30, rounds=3)
        assert 0 <= result["win_rate_pct"] <= 100


class TestOptimizeWeights:
    """权重优化测试。"""

    def _mock_all(self, monkeypatch, sample_finance, kline_uptrend):
        import backtest

        quote_obj = _make_quote_obj()
        finance_obj = _make_finance_obj()


        monkeypatch.setattr(backtest, "get_finance", lambda code: [finance_obj])
        monkeypatch.setattr(backtest, "get_kline", lambda code, scale=240, datalen=70: _make_kline_bars([10+i*0.3 for i in range(70)]))

    def test_restores_original_weights(self, monkeypatch, sample_finance, kline_uptrend):
        """验证优化后原始权重被恢复。"""
        import backtest
        import screener
        self._mock_all(monkeypatch, sample_finance, kline_uptrend)

        original = {k: v for k, v in screener.STRATEGIES["balanced"].items()}
        backtest.optimize_weights(["sh600519"], "balanced", top_n=1, days=10)
        assert screener.STRATEGIES["balanced"] == original

    def test_restores_weights_on_exception(self, monkeypatch, sample_finance, kline_uptrend):
        """验证异常时也能恢复权重。"""
        import backtest
        import screener
        self._mock_all(monkeypatch, sample_finance, kline_uptrend)

        original = {k: v for k, v in screener.STRATEGIES["balanced"].items()}

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

    def test_returns_best_weights(self, monkeypatch, sample_finance, kline_uptrend):
        import backtest
        self._mock_all(monkeypatch, sample_finance, kline_uptrend)

        result = backtest.optimize_weights(["sh600519"], "balanced", top_n=1, days=10)
        assert "best_weights" in result
        assert "best_sharpe" in result
        assert "baseline_sharpe" in result
        assert "improvement" in result
        assert "all_results" in result


class TestCompareStrategies:
    """策略比较测试。"""

    def test_compares_all_strategies(self, monkeypatch, sample_finance, kline_uptrend):
        import backtest

        quote_obj = _make_quote_obj()
        finance_obj = _make_finance_obj()


        monkeypatch.setattr(backtest, "get_finance", lambda code: [finance_obj])
        monkeypatch.setattr(backtest, "get_kline", lambda code, scale=240, datalen=70: _make_kline_bars([10+i*0.3 for i in range(70)]))

        results = backtest.compare_strategies(["sh600519"], top_n=1, days=10, rounds=2)
        assert len(results) == 5
        assert "balanced" in results
        assert "quality_value" in results
        assert "growth_momentum" in results
        assert "defensive" in results
        assert "turning_point" in results
