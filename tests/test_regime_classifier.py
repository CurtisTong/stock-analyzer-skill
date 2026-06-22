"""市场状态分类器测试。"""

import pytest
from strategies.regime.classifier import RegimeState, classify_regime


class TestRegimeState:
    """RegimeState 枚举。"""

    def test_bull_label(self):
        assert RegimeState.BULL.label == "牛市"

    def test_bear_label(self):
        assert RegimeState.BEAR.label == "熊市"

    def test_range_label(self):
        assert RegimeState.RANGE.label == "震荡"

    def test_panic_label(self):
        assert RegimeState.PANIC.label == "冰点"

    def test_string_value(self):
        assert RegimeState.BULL == "bull"
        assert RegimeState.BEAR == "bear"


class TestClassifyRegime:
    """classify_regime 信号分类。"""

    def test_panic_high_volatility(self):
        """高波动率触发 panic。"""
        signals = {
            "index_trend": 0.0,
            "volatility": 40,
            "breadth": 0.5,
            "turnover": 10000,
        }
        assert classify_regime(signals) == RegimeState.PANIC

    def test_panic_extreme_low_turnover(self):
        """极端缩量 + 大跌触发 panic。"""
        signals = {
            "index_trend": -0.5,
            "volatility": 20,
            "breadth": 0.3,
            "turnover": 3000,
        }
        assert classify_regime(signals) == RegimeState.PANIC

    def test_bull_strong_trend(self):
        """强趋势 + 宽度扩张 = bull。"""
        signals = {
            "index_trend": 0.5,
            "volatility": 15,
            "breadth": 0.6,
            "turnover": 10000,
        }
        assert classify_regime(signals) == RegimeState.BULL

    def test_bear_downtrend(self):
        """下跌趋势 + 宽度收缩 = bear。"""
        signals = {
            "index_trend": -0.3,
            "volatility": 20,
            "breadth": 0.4,
            "turnover": 8000,
        }
        assert classify_regime(signals) == RegimeState.BEAR

    def test_range_default(self):
        """其他情况 = range。"""
        signals = {
            "index_trend": 0.0,
            "volatility": 15,
            "breadth": 0.5,
            "turnover": 8000,
        }
        assert classify_regime(signals) == RegimeState.RANGE

    def test_range_weak_trend(self):
        """弱趋势不满足 bull/bear 条件 = range。"""
        signals = {
            "index_trend": 0.1,
            "volatility": 10,
            "breadth": 0.5,
            "turnover": 8000,
        }
        assert classify_regime(signals) == RegimeState.RANGE

    def test_empty_signals(self):
        """空信号默认为 range。"""
        assert classify_regime({}) == RegimeState.RANGE

    def test_panic_priority_over_bull(self):
        """panic 优先于 bull。"""
        signals = {
            "index_trend": 0.5,
            "volatility": 40,
            "breadth": 0.6,
            "turnover": 10000,
        }
        assert classify_regime(signals) == RegimeState.PANIC

    def test_panic_priority_over_bear(self):
        """panic 优先于 bear。"""
        signals = {
            "index_trend": -0.5,
            "volatility": 40,
            "breadth": 0.3,
            "turnover": 8000,
        }
        assert classify_regime(signals) == RegimeState.PANIC

    def test_boundary_volatility_35(self):
        """波动率 = 35 触发 panic。"""
        signals = {
            "index_trend": 0.0,
            "volatility": 35,
            "breadth": 0.5,
            "turnover": 10000,
        }
        assert classify_regime(signals) == RegimeState.PANIC

    def test_boundary_volatility_34(self):
        """波动率 = 34 不触发 panic（除非其他条件满足）。"""
        signals = {
            "index_trend": 0.0,
            "volatility": 34,
            "breadth": 0.5,
            "turnover": 10000,
        }
        assert classify_regime(signals) == RegimeState.RANGE

    def test_boundary_bull_trend(self):
        """trend = 0.31, breadth = 0.56 = bull。"""
        signals = {
            "index_trend": 0.31,
            "volatility": 15,
            "breadth": 0.56,
            "turnover": 10000,
        }
        assert classify_regime(signals) == RegimeState.BULL

    def test_boundary_bear_trend(self):
        """trend = -0.21, breadth = 0.44 = bear。"""
        signals = {
            "index_trend": -0.21,
            "volatility": 15,
            "breadth": 0.44,
            "turnover": 10000,
        }
        assert classify_regime(signals) == RegimeState.BEAR
