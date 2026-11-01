"""基准按日期对齐测试（v1.24.0 复审修复）。

背景：基准侧原按固定 holding_days 切连续日线块，策略侧按 date 分组——
两者只在网格严格对齐时等价。实测策略第 3 期起点 07-31 被拿去与基准
第 3 块（08-13..08-26）相减，错位约两周。
"""

from __future__ import annotations

import pytest


class TestSliceBenchmarkByPeriod:
    def _setup(self):
        # 基准 10 个交易日，每日 +1%
        dates = [f"2026-07-{d:02d}" for d in range(1, 11)]
        returns = [0.01] * 10
        return dates, returns

    def test_aligned_periods(self):
        from backtest.metrics import _slice_benchmark_by_period

        dates, returns = self._setup()
        periods = [
            {"start": "2026-07-01", "holding_days": 3},
            {"start": "2026-07-04", "holding_days": 3},
        ]
        out = _slice_benchmark_by_period(dates, returns, periods, fallback_holding_days=3)
        # 每期 3 天 +1% 连乘 → 1.01^3 - 1 = 3.0301%
        assert out[0] == pytest.approx(3.0301, abs=1e-3)
        assert out[1] == pytest.approx(3.0301, abs=1e-3)

    def test_shifted_period_uses_its_own_dates(self):
        """错位的期必须按自己的日期取基准，不能落到别的期区间上。"""
        from backtest.metrics import _slice_benchmark_by_period

        dates = [f"2026-07-{d:02d}" for d in range(1, 11)]
        # 前 4 天 +1%，第 5 天起 -10%
        returns = [0.01, 0.01, 0.01, 0.01, -0.10, -0.10, -0.10, -0.10, -0.10, -0.10]
        periods = [
            {"start": "2026-07-01", "holding_days": 3},  # 全 +1% → +3.03%
            {"start": "2026-07-05", "holding_days": 3},  # 全 -10% → -27.1%
        ]
        out = _slice_benchmark_by_period(dates, returns, periods, fallback_holding_days=3)
        assert out[0] == pytest.approx(3.0301, abs=1e-3)
        assert out[1] == pytest.approx((0.9**3 - 1) * 100, abs=1e-2)

    def test_start_date_not_in_benchmark(self):
        """选股日不在基准序列里时补 0（不拿别的期的收益充数）。"""
        from backtest.metrics import _slice_benchmark_by_period

        dates, returns = self._setup()
        periods = [{"start": "2026-08-01", "holding_days": 3}]
        out = _slice_benchmark_by_period(dates, returns, periods, fallback_holding_days=3)
        assert out == [0.0]

    def test_varying_holding_days(self):
        """每期持有天数不同时按各自的天数切。"""
        from backtest.metrics import _slice_benchmark_by_period

        dates, returns = self._setup()
        periods = [
            {"start": "2026-07-01", "holding_days": 2},
            {"start": "2026-07-03", "holding_days": 4},
        ]
        out = _slice_benchmark_by_period(dates, returns, periods, fallback_holding_days=3)
        assert out[0] == pytest.approx((1.01**2 - 1) * 100, abs=1e-3)
        assert out[1] == pytest.approx((1.01**4 - 1) * 100, abs=1e-3)


class TestSliceBenchmarkOffByOne:
    """基准期起点口径（v1.27.0 修复）。

    策略在**选股日收盘**入场（entry_price = bars[start].close），持有 N 天
    覆盖的是选股日**次日**起的 N 个日收益。选股日当天的收益发生在入场
    之前，不属于持仓期。原实现从选股日当天起切，使基准期整体前移一天
    （实测单期偏差可达 3pp、方向可翻转），污染 IR/alpha/beta/超额夏普。
    """

    def _series(self):
        """构造可区分的基准序列：每天收益各不相同。

        dates[i] 对应的收益 returns[i] 是**该日当天**的日收益。
        """
        dates = [f"2026-07-{d:02d}" for d in range(1, 8)]
        returns = [0.10, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06]
        return dates, returns

    def test_period_starts_from_day_after_selection(self):
        """选股日当天的收益不计入该期基准。"""
        from backtest.metrics import _slice_benchmark_by_period

        dates, returns = self._series()
        periods = [{"start": "2026-07-02", "holding_days": 3}]
        out = _slice_benchmark_by_period(dates, returns, periods, fallback_holding_days=3)
        # 正确口径：选股日 07-02 次日起 3 天 = 07-03, 07-04, 07-05
        expected = ((1 + returns[2]) * (1 + returns[3]) * (1 + returns[4]) - 1) * 100
        assert out[0] == pytest.approx(expected, abs=1e-6)

    def test_selection_day_return_excluded(self):
        """选股日当天收益（returns[idx]）必须被排除——它是入场前的涨跌。"""
        from backtest.metrics import _slice_benchmark_by_period

        dates, returns = self._series()
        periods = [{"start": "2026-07-02", "holding_days": 2}]
        out = _slice_benchmark_by_period(dates, returns, periods, fallback_holding_days=2)
        # 若错误地包含选股日（+10%），结果会明显更高
        wrong = ((1 + returns[1]) * (1 + returns[2]) - 1) * 100
        assert out[0] != pytest.approx(wrong, abs=1e-3)
        assert out[0] == pytest.approx(((1 + returns[2]) * (1 + returns[3]) - 1) * 100, abs=1e-6)

    def test_last_day_of_benchmark_series(self):
        """选股日靠近序列末端时，取到实际可用的天数，不越界报错。"""
        from backtest.metrics import _slice_benchmark_by_period

        dates, returns = self._series()
        periods = [{"start": "2026-07-06", "holding_days": 3}]
        out = _slice_benchmark_by_period(dates, returns, periods, fallback_holding_days=3)
        # 07-06 次日起只有 07-07 一天可用
        assert out[0] == pytest.approx(returns[6] * 100, abs=1e-6)


class TestEnginePeriodDates:
    def test_simulate_returns_period_dates(self):
        """引擎回传每期的 start + holding_days（基准对齐的前提）。"""
        from backtest.engine import SimContext, simulate_strategy
        from data.types import KlineBar

        from datetime import datetime, timedelta

        def _mock_kline(code, scale=240, datalen=140):
            today = datetime.now()
            bars = []
            for i in range(140):
                d = today - timedelta(days=140 - i)
                bars.append(
                    KlineBar(
                        day=d.strftime("%Y-%m-%d"),
                        close=10 + i * 0.3,
                        open=10 + i * 0.3,
                        high=10 + i * 0.3,
                        low=10 + i * 0.3,
                        volume=1000,
                    )
                )
            return bars

        import backtest.engine as engine_mod

        orig = engine_mod.get_kline
        engine_mod.get_kline = _mock_kline
        try:
            result = simulate_strategy(
                SimContext(
                    strategy_name="balanced",
                    codes=["sh600519", "sh600520", "sh600521"],
                    top_n=2,
                    holding_days=10,
                    total_days=60,
                )
            )
        finally:
            engine_mod.get_kline = orig

        assert "error" not in result, result.get("error")
        periods = result.get("period_dates")
        assert periods, "引擎必须回传 period_dates"
        assert len(periods) == len(result["returns"])
        for p in periods:
            assert p["start"]
            assert p["holding_days"] > 0
        # 期的起点应互不相同且递增
        starts = [p["start"] for p in periods]
        assert starts == sorted(starts)
