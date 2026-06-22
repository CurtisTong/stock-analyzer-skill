"""strategies/regime/detector.py 单元测试：市场信号检测。"""

import pytest
from unittest.mock import patch, MagicMock
from data.types import KlineBar


def _make_bars(closes: list, amounts: list = None) -> list:
    """构造 KlineBar 列表。"""
    bars = []
    for i, c in enumerate(closes):
        amt = amounts[i] if amounts else c * 1000000
        bars.append(
            KlineBar(
                day=f"2025-06-{i+1:02d}",
                open=c * 0.99,
                high=c * 1.01,
                low=c * 0.98,
                close=c,
                amount=amt,
            )
        )
    return bars


class TestZeroSignals:
    """_zero_signals 测试。"""

    def test_returns_zero_dict(self):
        from strategies.regime.detector import _zero_signals

        result = _zero_signals()
        assert result["index_trend"] == 0.0
        assert result["volatility"] == 0.0
        assert result["breadth"] == 0.5
        assert result["turnover"] == 0.0


class TestDetectSignals:
    """detect_signals 测试。"""

    def test_returns_zero_on_fetch_error(self):
        from strategies.regime.detector import detect_signals

        with patch(
            "strategies.regime.detector.get_kline", side_effect=Exception("网络错误")
        ):
            result = detect_signals()

        assert result["index_trend"] == 0.0
        assert result["volatility"] == 0.0

    def test_returns_zero_on_empty_data(self):
        from strategies.regime.detector import detect_signals

        with patch("strategies.regime.detector.get_kline", return_value=[]):
            result = detect_signals()

        assert result["index_trend"] == 0.0

    def test_returns_zero_on_insufficient_data(self):
        from strategies.regime.detector import detect_signals

        bars = _make_bars([100.0] * 10)  # < 20 bars
        with patch("strategies.regime.detector.get_kline", return_value=bars):
            result = detect_signals()

        assert result["index_trend"] == 0.0

    def test_uptrend_signals(self):
        """上升趋势应产生正 index_trend。"""
        from strategies.regime.detector import detect_signals

        # 构造上升序列：从 100 涨到 120
        closes = [100 + i * 0.35 for i in range(60)]
        bars = _make_bars(closes)
        with patch("strategies.regime.detector.get_kline", return_value=bars):
            result = detect_signals()

        assert result["index_trend"] > 0
        assert result["volatility"] >= 0
        assert 0 <= result["breadth"] <= 1

    def test_downtrend_signals(self):
        """下降趋势应产生负 index_trend。"""
        from strategies.regime.detector import detect_signals

        closes = [120 - i * 0.35 for i in range(60)]
        bars = _make_bars(closes)
        with patch("strategies.regime.detector.get_kline", return_value=bars):
            result = detect_signals()

        assert result["index_trend"] < 0

    def test_returns_all_keys(self):
        from strategies.regime.detector import detect_signals

        closes = [100 + i * 0.1 for i in range(60)]
        bars = _make_bars(closes)
        with patch("strategies.regime.detector.get_kline", return_value=bars):
            result = detect_signals()

        assert set(result.keys()) == {
            "index_trend",
            "volatility",
            "breadth",
            "turnover",
        }

    def test_index_trend_clamped(self):
        """index_trend 应在 [-1, 1] 范围内。"""
        from strategies.regime.detector import detect_signals

        closes = [100 + i * 2 for i in range(60)]
        bars = _make_bars(closes)
        with patch("strategies.regime.detector.get_kline", return_value=bars):
            result = detect_signals()

        assert -1.0 <= result["index_trend"] <= 1.0

    def test_turnover_in_yi(self):
        """turnover 应以亿元为单位。"""
        from strategies.regime.detector import detect_signals

        closes = [100.0] * 60
        amounts = [2e8] * 60  # 2亿/天
        bars = _make_bars(closes, amounts)
        with patch("strategies.regime.detector.get_kline", return_value=bars):
            result = detect_signals()

        assert abs(result["turnover"] - 2.0) < 0.1
