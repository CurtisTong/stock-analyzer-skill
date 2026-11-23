"""v1.24.0 复审修复的形态库回归测试。

覆盖：
- 同一根 K 同时产出看涨与看跌形态（锤子线 vs 吊颈线、射击之星 vs 倒锤头）
- 孕线方向布尔颠倒（真正的反色孕线被漏判）
- truncated 阈值与展示位上限不一致
- review P2（docs/code-review-2026-11-21.md §4.2）：回测报告夏普/复利/回撤口径
"""

from __future__ import annotations

import pytest

from strategies.patterns.classic import _trend, detect_classic_patterns


def _bars(candles):
    records = []
    for i, (o, c, h, lo) in enumerate(candles):
        records.append({"day": f"2026-01-{i + 1:02d}", "open": o, "close": c, "high": h, "low": lo, "volume": 1000})
    return records, [r["close"] for r in records]


def _names(records, closes):
    return {s["name"] for s in detect_classic_patterns(records, closes)}


def _types(records, closes):
    return {s["name"]: s["type"] for s in detect_classic_patterns(records, closes)}


class TestTrendPrerequisite:
    """教科书趋势前提：反转形态必须出现在对应趋势末端。"""

    def test_uptrend_long_lower_shadow_is_hanging_man_not_hammer(self):
        """上涨趋势中的长下影 → 吊颈线（看跌），不得同时出锤子线（看涨）。"""
        # 前 5 根稳步上涨，第 6 根长下影小实体
        candles = [
            (10.0, 10.0, 10.1, 9.9),
            (10.0, 10.2, 10.3, 9.9),
            (10.2, 10.4, 10.5, 10.1),
            (10.4, 10.6, 10.7, 10.3),
            (10.6, 10.8, 10.9, 10.5),
            (11.0, 11.05, 11.06, 10.3),  # 长下影（10.3），上影极短
        ]
        records, closes = _bars(candles)
        names = _names(records, closes)
        assert "吊颈线" in names
        assert "锤子线" not in names, "同一根 K 同时产出看涨与看跌形态"

    def test_downtrend_long_lower_shadow_is_hammer(self):
        """下跌趋势中的长下影 → 锤子线（看涨），不得出吊颈线。"""
        candles = [
            (11.0, 11.0, 11.1, 10.9),
            (10.8, 10.8, 10.9, 10.7),
            (10.6, 10.6, 10.7, 10.5),
            (10.4, 10.4, 10.5, 10.3),
            (10.2, 10.2, 10.3, 10.1),
            (10.0, 9.95, 9.96, 9.3),  # 长下影（9.3），上影极短
        ]
        records, closes = _bars(candles)
        names = _names(records, closes)
        assert "锤子线" in names
        assert "吊颈线" not in names

    def test_no_conflicting_directions_on_same_candle(self):
        """任一根 K 上不得同时出现看涨与看跌的经典形态。"""
        candles = [
            (10.0, 10.0, 10.1, 9.9),
            (10.0, 10.2, 10.3, 9.9),
            (10.2, 10.4, 10.5, 10.1),
            (10.4, 10.6, 10.7, 10.3),
            (10.6, 10.8, 10.9, 10.5),
            (11.0, 11.05, 11.06, 10.3),
        ]
        records, closes = _bars(candles)
        types = _types(records, closes)
        bullish = {n for n, t in types.items() if t == "看涨"}
        bearish = {n for n, t in types.items() if t == "看跌"}
        assert not (bullish and bearish), types

    def test_trend_helper(self):
        closes = [10.0, 9.8, 9.5, 9.2, 9.0, 8.8]
        assert _trend(closes, 5) == "down"
        up = [10.0, 10.2, 10.5, 10.8, 11.0, 11.2]
        assert _trend(up, 5) == "up"
        # 数据不足时返回 None（调用方不加约束）
        assert _trend([10.0, 9.9], 1) is None


class TestHaramiDirection:
    """孕线：方向相反才构成反转预警。"""

    def test_bullish_harami_detected(self):
        """前阴后阳的小实体孕线必须被识别（原实现漏判）。"""
        records, closes = _bars([(10.5, 10.0, 10.6, 9.9), (10.1, 10.2, 10.3, 9.95)])
        assert "孕线" in _names(records, closes)

    def test_bearish_harami_detected(self):
        """前阳后阴的小实体孕线必须被识别。"""
        records, closes = _bars([(10.0, 10.5, 10.6, 9.9), (10.4, 10.3, 10.5, 10.2)])
        assert "孕线" in _names(records, closes)


class TestTruncatedThreshold:
    """truncated 阈值必须与展示位上限一致。"""

    def test_threshold_matches_display_limit(self):
        from strategies.patterns import PATTERN_DISPLAY_LIMIT

        assert PATTERN_DISPLAY_LIMIT == 10

    def test_truncated_false_when_within_limit(self):
        from strategies.patterns import PatternInput, detect_all_local_patterns

        # 构造若干十字星（中性形态）使其总数落在 6-10 区间
        candles = [(10.0, 10.0, 10.1, 9.9)] * 8
        records, closes = _bars(candles)
        inp = PatternInput(
            records=records,
            closes=closes,
            highs=[r["high"] for r in records],
            lows=[r["low"] for r in records],
            volumes=[1000] * len(closes),
            mas={},
            code="sh600519",
        )
        result = detect_all_local_patterns(inp)
        assert result["detected_count"] <= 10
        assert result["truncated"] is False


class TestBacktestReportMetrics:
    """review 条目 P2：夏普年化 + 无 rf、复利收益、复利权益回撤。"""

    @staticmethod
    def _trades(*returns):
        return [
            {
                "return_pct": r,
                "buy_date": "2026-01-01",
                "buy_price": 10.0,
                "sell_date": "2026-01-08",
                "sell_price": 10.0 * (1 + r / 100),
                "signal": "测试信号",
            }
            for r in returns
        ]

    def test_total_return_is_compounded_not_summed(self):
        # review P2：+10% 与 -10% 简单加总是 0，复利应为 -1%
        from strategies.patterns.backtest_report import calculate_advanced_stats

        stats = calculate_advanced_stats(self._trades(10.0, -10.0))
        assert stats["total_return"] == -1.0

    def test_max_drawdown_uses_compound_equity_curve(self):
        # review P2：-20% 后 +30% 的线性累计回撤为 0，复利权益峰值回撤应为 20%
        from strategies.patterns.backtest_report import calculate_advanced_stats

        stats = calculate_advanced_stats(self._trades(-20.0, 30.0))
        assert stats["max_drawdown"] == 20.0

    def test_max_drawdown_differs_from_linear_cumulative(self):
        # review P2：+20/-20/-20 线性口径 40%，复利口径 (1.2-0.768)/1.2 = 36%
        from strategies.patterns.backtest_report import calculate_advanced_stats

        stats = calculate_advanced_stats(self._trades(20.0, -20.0, -20.0))
        assert stats["max_drawdown"] == pytest.approx(36.0, abs=0.01)

    def test_sharpe_is_annualized_by_holding_days(self):
        # review P2：sqrt(252/holding_days) 年化，持有 5 日应为持有 20 日的 2 倍
        from strategies.patterns.backtest_report import calculate_advanced_stats

        trades = self._trades(1.0, 2.0, -0.5, 1.5)
        short = calculate_advanced_stats(trades, holding_days=5)["sharpe_ratio"]
        long = calculate_advanced_stats(trades, holding_days=20)["sharpe_ratio"]
        assert short == pytest.approx(long * 2, rel=0.02)

    def test_sharpe_subtracts_risk_free_rate(self):
        # review P2：无风险利率必须进入夏普分子，rf 越高夏普越低
        from strategies.patterns.backtest_report import calculate_advanced_stats

        trades = self._trades(1.0, 2.0, -0.5, 1.5)
        raw = calculate_advanced_stats(trades, holding_days=5)["sharpe_ratio"]
        with_rf = calculate_advanced_stats(trades, holding_days=5, risk_free_rate=0.05)["sharpe_ratio"]
        assert with_rf < raw

    def test_output_field_names_unchanged(self):
        # review P2：口径修正不得改动任何输出字段名
        from strategies.patterns.backtest_report import calculate_advanced_stats

        stats = calculate_advanced_stats(self._trades(1.0, -0.5))
        assert set(stats) == {
            "total_trades",
            "win_count",
            "loss_count",
            "win_rate",
            "total_return",
            "avg_return",
            "avg_win",
            "avg_loss",
            "max_win",
            "max_loss",
            "profit_factor",
            "max_consecutive_wins",
            "max_consecutive_losses",
            "sharpe_ratio",
            "max_drawdown",
        }

    def test_report_shows_compound_curve(self, monkeypatch):
        # review P2：报告正文的累计收益曲线也要用复利口径
        from strategies.patterns import backtest_report as br

        monkeypatch.setattr(br, "backtest_strategy", lambda *a, **kw: self._trades(10.0, -10.0))
        report = br.generate_backtest_report([], "测试股")
        assert "复利累计收益曲线" in report
        assert "累计收益: -1.0%" in report
