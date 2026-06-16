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
    defaults = dict(
        code=code,
        name=name,
        price=price,
        pe=25.6,
        pb=8.2,
        total_cap=22600,
        circulating_cap=22600,
        amount=2234567,
        turnover=0.15,
        change_pct=0.56,
    )
    defaults.update(kwargs)
    return Quote(**defaults)


def _make_kline_bars(prices):
    """从价格列表构造 KlineBar 列表。"""
    return [
        KlineBar(day=f"2025-01-{i+1:02d}", close=p, open=p, high=p, low=p)
        for i, p in enumerate(prices)
    ]


def _make_finance_obj(**kwargs):
    """构造 FinanceRecord dataclass。"""
    defaults = dict(
        eps=50.0,
        roe=30.5,
        revenue_yoy=15.2,
        net_profit_yoy=18.3,
        gross_margin=91.5,
        debt_ratio=18.7,
        ocf_per_share=55.0,
    )
    defaults.update(kwargs)
    return FinanceRecord(**defaults)


class TestFetchHistoricalReturns:
    """历史收益率序列计算。"""

    def test_empty_records_returns_empty(self, monkeypatch):
        import backtest

        monkeypatch.setattr(
            backtest, "get_kline", lambda code, scale=240, datalen=65: []
        )
        result = backtest.fetch_historical_returns("sh600519", 60)
        assert result == []

    def test_single_record_returns_empty(self, monkeypatch):
        import backtest

        bars = _make_kline_bars([100.0])
        monkeypatch.setattr(
            backtest, "get_kline", lambda code, scale=240, datalen=65: bars
        )
        result = backtest.fetch_historical_returns("sh600519", 60)
        assert result == []

    def test_calculates_returns_correctly(self, monkeypatch):
        import backtest

        bars = _make_kline_bars([100.0, 110.0, 99.0, 108.9])
        monkeypatch.setattr(
            backtest, "get_kline", lambda code, scale=240, datalen=65: bars
        )
        result = backtest.fetch_historical_returns("sh600519", 60)
        assert len(result) == 3
        assert result[0] == pytest.approx(0.1)  # +10%
        assert result[1] == pytest.approx(-0.1)  # -10%
        assert result[2] == pytest.approx(0.1)  # +10%

    def test_zero_prev_close_skipped(self, monkeypatch):
        import backtest

        bars = _make_kline_bars([0.0, 100.0, 110.0])
        monkeypatch.setattr(
            backtest, "get_kline", lambda code, scale=240, datalen=65: bars
        )
        result = backtest.fetch_historical_returns("sh600519", 60)
        assert len(result) == 1
        assert result[0] == pytest.approx(0.1)


class TestSimulateStrategy:
    """策略模拟测试。"""

    def _mock_all(self, monkeypatch, sample_finance_dict, kline_uptrend):
        """统一 mock 数据层和 screener 适配器。"""
        import backtest
        import screener
        from datetime import datetime, timedelta

        quote_obj = _make_quote_obj()
        finance_obj = _make_finance_obj()

        monkeypatch.setattr(backtest, "get_finance", lambda code: [finance_obj])
        # 滚动窗口需要至少 60+holding_days 根 K 线，日期必须在 stale_cutoff 内
        today = datetime.now()

        def _mock_kline(code, scale=240, datalen=140):
            n = max(datalen, 140)
            bars = []
            for i in range(n):
                d = today - timedelta(days=n - i)
                bars.append(
                    KlineBar(
                        day=d.strftime("%Y-%m-%d"),
                        close=10 + i * 0.3,
                        open=10 + i * 0.3,
                        high=10 + i * 0.3,
                        low=10 + i * 0.3,
                    )
                )
            return bars

        monkeypatch.setattr(backtest, "get_kline", _mock_kline)

    def test_returns_all_fields(self, monkeypatch, sample_finance, kline_uptrend):
        import backtest

        self._mock_all(monkeypatch, sample_finance, kline_uptrend)

        result = backtest.simulate_strategy(
            "balanced", ["sh600519"], top_n=1, holding_days=5
        )
        assert "strategy" in result
        assert "selections" in result
        assert "returns" in result
        assert "avg_return_pct" in result
        assert "total_periods" in result
        assert result["strategy"] == "balanced"

    def test_no_kline_returns_error(self, monkeypatch):
        """K 线数据不足时返回错误。"""
        import backtest

        monkeypatch.setattr(
            backtest, "get_kline", lambda code, scale=240, datalen=70: []
        )
        monkeypatch.setattr(backtest, "get_finance", lambda code: [])

        result = backtest.simulate_strategy("balanced", ["sh600519"])
        assert "error" in result

    def test_rolling_window_generates_returns(
        self, monkeypatch, sample_finance, kline_uptrend
    ):
        """验证滚动窗口生成多个收益周期。"""
        import backtest
        import screener

        finance_obj = _make_finance_obj()
        quote_obj = _make_quote_obj()
        from datetime import datetime, timedelta

        monkeypatch.setattr(backtest, "get_finance", lambda code: [finance_obj])
        today = datetime.now()

        def _mock_kline(code, scale=240, datalen=140):
            n = max(datalen, 140)
            bars = []
            for i in range(n):
                d = today - timedelta(days=n - i)
                bars.append(
                    KlineBar(
                        day=d.strftime("%Y-%m-%d"),
                        close=10 + i * 0.2,
                        open=10 + i * 0.2,
                        high=10 + i * 0.2,
                        low=10 + i * 0.2,
                    )
                )
            return bars

        monkeypatch.setattr(backtest, "get_kline", _mock_kline)

        result = backtest.simulate_strategy(
            "balanced", ["sh600519"], top_n=1, holding_days=10
        )
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
        from datetime import datetime, timedelta

        today = datetime.now()

        def _mock_kline(code, scale=240, datalen=140):
            n = max(datalen, 140)
            bars = []
            for i in range(n):
                d = today - timedelta(days=n - i)
                bars.append(
                    KlineBar(
                        day=d.strftime("%Y-%m-%d"),
                        close=10 + i * 0.3,
                        open=10 + i * 0.3,
                        high=10 + i * 0.3,
                        low=10 + i * 0.3,
                    )
                )
            return bars

        monkeypatch.setattr(backtest, "get_kline", _mock_kline)

        backtest.simulate_strategy("balanced", ["sh600519"], top_n=1, holding_days=5)
        assert finance_called["count"] > 0


class TestRunBacktest:
    """多轮回测测试。"""

    def _mock_all(self, monkeypatch, sample_finance, kline_uptrend):
        import backtest
        from datetime import datetime, timedelta

        finance_obj = _make_finance_obj()

        monkeypatch.setattr(backtest, "get_finance", lambda code: [finance_obj])
        today = datetime.now()

        def _mock_kline(code, scale=240, datalen=140):
            n = max(datalen, 140)
            bars = []
            for i in range(n):
                d = today - timedelta(days=n - i)
                bars.append(
                    KlineBar(
                        day=d.strftime("%Y-%m-%d"),
                        close=10 + i * 0.3,
                        open=10 + i * 0.3,
                        high=10 + i * 0.3,
                        low=10 + i * 0.3,
                    )
                )
            return bars

        monkeypatch.setattr(backtest, "get_kline", _mock_kline)

    def test_returns_statistical_fields(
        self, monkeypatch, sample_finance, kline_uptrend
    ):
        import backtest

        self._mock_all(monkeypatch, sample_finance, kline_uptrend)

        result = backtest.run_backtest(
            "balanced", ["sh600519"], top_n=1, days=30, rounds=3
        )
        assert "total_return_pct" in result
        assert "avg_return_pct" in result
        assert "win_rate_pct" in result
        assert "sharpe_ratio" in result
        assert "max_drawdown_pct" in result
        assert "round_details" in result

    def test_win_rate_between_0_and_100(
        self, monkeypatch, sample_finance, kline_uptrend
    ):
        import backtest

        self._mock_all(monkeypatch, sample_finance, kline_uptrend)

        result = backtest.run_backtest(
            "balanced", ["sh600519"], top_n=1, days=30, rounds=3
        )
        assert 0 <= result["win_rate_pct"] <= 100


class TestOptimizeWeights:
    """权重优化测试。"""

    def _mock_all(self, monkeypatch, sample_finance, kline_uptrend):
        import backtest
        from datetime import datetime, timedelta

        finance_obj = _make_finance_obj()

        monkeypatch.setattr(backtest, "get_finance", lambda code: [finance_obj])
        today = datetime.now()

        def _mock_kline(code, scale=240, datalen=140):
            n = max(datalen, 140)
            bars = []
            for i in range(n):
                d = today - timedelta(days=n - i)
                bars.append(
                    KlineBar(
                        day=d.strftime("%Y-%m-%d"),
                        close=10 + i * 0.3,
                        open=10 + i * 0.3,
                        high=10 + i * 0.3,
                        low=10 + i * 0.3,
                    )
                )
            return bars

        monkeypatch.setattr(backtest, "get_kline", _mock_kline)

    def test_restores_original_weights(
        self, monkeypatch, sample_finance, kline_uptrend
    ):
        """验证优化后原始权重被恢复。"""
        import backtest
        import screener

        self._mock_all(monkeypatch, sample_finance, kline_uptrend)

        original = {k: v for k, v in screener.STRATEGIES["balanced"].items()}
        backtest.optimize_weights(["sh600519"], "balanced", top_n=1, days=10)
        assert screener.STRATEGIES["balanced"] == original

    def test_restores_weights_on_exception(
        self, monkeypatch, sample_finance, kline_uptrend
    ):
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
        from datetime import datetime, timedelta

        finance_obj = _make_finance_obj()

        monkeypatch.setattr(backtest, "get_finance", lambda code: [finance_obj])
        today = datetime.now()

        def _mock_kline(code, scale=240, datalen=140):
            n = max(datalen, 140)
            bars = []
            for i in range(n):
                d = today - timedelta(days=n - i)
                bars.append(
                    KlineBar(
                        day=d.strftime("%Y-%m-%d"),
                        close=10 + i * 0.3,
                        open=10 + i * 0.3,
                        high=10 + i * 0.3,
                        low=10 + i * 0.3,
                    )
                )
            return bars

        monkeypatch.setattr(backtest, "get_kline", _mock_kline)

        results = backtest.compare_strategies(["sh600519"], top_n=1, days=10, rounds=2)
        assert len(results) == 5
        assert "balanced" in results
        assert "quality_value" in results
        assert "growth_momentum" in results
        assert "defensive" in results
        assert "turning_point" in results


# ═══════════════════════════════════════════════════════════════
# 6. 纯计算函数（无外部依赖）
# ═══════════════════════════════════════════════════════════════
class TestCalcRsi:
    """RSI（Wilder 平滑）纯计算。"""

    def test_insufficient_data_returns_50(self):
        """数据不足 period+1 时返回 50（中性）。"""
        import backtest

        assert backtest._calc_rsi([1, 2, 3], 14) == 50.0

    def test_all_up_returns_100(self):
        """连续上涨 → RSI = 100。"""
        import backtest

        closes = [10.0 + i for i in range(20)]
        assert backtest._calc_rsi(closes, 14) == 100.0

    def test_all_down_returns_zero(self):
        """连续下跌 → RSI 接近 0。"""
        import backtest

        closes = [30.0 - i for i in range(20)]
        rsi = backtest._calc_rsi(closes, 14)
        assert rsi < 1.0

    def test_mixed_range(self):
        """震荡行情 → RSI 在 20-80 之间。"""
        import backtest
        import math

        closes = [50.0 + 5 * math.sin(i * 0.3) for i in range(40)]
        rsi = backtest._calc_rsi(closes, 14)
        assert 20 <= rsi <= 80, f"Expected 20-80, got {rsi:.1f}"


class TestBuildHistQuote:
    """历史行情 dict 构造。"""

    def test_basic_construction(self):
        import backtest

        bars = _make_kline_bars([10.0, 11.0, 12.0, 13.0, 14.0, 15.0])
        fin = {"eps": 2.0, "bps": 8.0, "total_cap": 500}
        result = backtest._build_hist_quote(bars, 3, fin, "sh600989")
        assert result["code"] == "sh600989"
        assert result["price"] == 13.0
        assert result["pe"] == 6.5  # 13.0 / 2.0
        assert result["pb"] == pytest.approx(1.625)  # 13.0 / 8.0
        assert result["total_cap"] == 500

    def test_pe_zero_when_no_eps(self):
        """eps = 0 → pe = 0。"""
        import backtest

        bars = _make_kline_bars([10.0, 11.0])
        result = backtest._build_hist_quote(bars, 0, {}, "sh600989")
        assert result["pe"] == 0
        assert result["pb"] == 0

    def test_amount_volume_from_bar(self):
        """amount/volume 取自 K 线。"""
        import backtest

        bars = [
            KlineBar(
                day="d1", open=10, high=10, low=10, close=10, volume=5000, amount=50000
            )
        ]
        result = backtest._build_hist_quote(bars, 0, {}, "sh600989")
        assert result["volume"] == 5000
        assert result["amount"] == 50000


class TestCalcDailyReturns:
    """持有期内日收益率序列。"""

    def test_length_matches_holding_days(self):
        import backtest

        bars = _make_kline_bars([10.0 + i * 0.1 for i in range(10)])
        result = backtest._calc_daily_returns(bars, 5, 3)
        assert len(result) == 3

    def test_returns_reflect_price_changes(self):
        """日收益 = (close[t] - close[t-1]) / close[t-1]。"""
        import backtest

        bars = _make_kline_bars([10.0, 11.0, 12.0, 13.0, 14.0, 15.0])
        result = backtest._calc_daily_returns(bars, 1, 3)
        assert abs(result[0] - 0.1) < 0.001  # (11-10)/10
        assert abs(result[1] - 1 / 11) < 0.001  # (12-11)/11
        assert abs(result[2] - 1 / 12) < 0.001  # (13-12)/12

    def test_empty_when_prev_close_zero(self):
        """前收为 0 时跳过。"""
        import backtest

        bars = _make_kline_bars([0.0, 10.0, 11.0])
        result = backtest._calc_daily_returns(bars, 1, 2)
        # bar[0].close=0 → bar[1] 跳过；bar[1].close=10 → bar[2] 记录
        assert len(result) == 1
        assert abs(result[0] - 0.1) < 0.001


class TestComputeMomentum:
    """动量因子纯计算。"""

    def test_insufficient_data_returns_50(self):
        """不足 60 根 K 线返回 50（中性）。"""
        import backtest

        bars = _make_kline_bars([10.0 + i * 0.1 for i in range(30)])
        assert backtest._compute_momentum_from_bars(bars) == 50.0

    def test_uptrend_high_momentum(self):
        """上升趋势 → 动量分 > 45（量比因子可能略微拉低总分）。"""
        import backtest

        bars = _make_kline_bars([10.0 + i * 0.5 for i in range(70)])
        score = backtest._compute_momentum_from_bars(bars)
        # 量比默认 1.0（volume=0 → vol_score=50），趋势 + RSI + 价格动量仍应偏高
        assert score > 45, f"Expected > 45 for uptrend, got {score:.1f}"

    def test_downtrend_low_momentum(self):
        """下降趋势 → 动量分 < 50。"""
        import backtest

        bars = _make_kline_bars([50.0 - i * 0.5 for i in range(70)])
        score = backtest._compute_momentum_from_bars(bars)
        assert score < 50, f"Expected < 50 for downtrend, got {score:.1f}"
