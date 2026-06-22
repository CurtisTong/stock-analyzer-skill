"""market_breadth.py 市场宽度分析测试。"""

import pytest
from unittest.mock import patch, MagicMock
from market_breadth import (
    _default_result,
    get_market_state,
    format_breadth,
)


class TestDefaultResult:
    """_default_result 默认结果。"""

    def test_all_zeros(self):
        result = _default_result()
        assert result["limit_up_count"] == 0
        assert result["limit_down_count"] == 0
        assert result["total_stocks"] == 0
        assert result["up_count"] == 0
        assert result["down_count"] == 0
        assert result["up_ratio"] == 0

    def test_keys_complete(self):
        result = _default_result()
        expected_keys = {
            "limit_up_count",
            "limit_down_count",
            "continuous_limit_height",
            "broken_limit_rate",
            "total_stocks",
            "up_count",
            "down_count",
            "up_ratio",
        }
        assert set(result.keys()) == expected_keys


class TestGetMarketState:
    """get_market_state 市场状态判断。"""

    def test_low_limit_up_retreat(self):
        """涨停 < 20 → 退潮。"""
        breadth = {
            "limit_up_count": 10,
            "limit_down_count": 5,
            "continuous_limit_height": 3,
            "broken_limit_rate": 20,
            "up_ratio": 1.0,
        }
        state = get_market_state(breadth)
        assert state["state"] == "退潮"

    def test_high_limit_up_main_rise(self):
        """涨停 > 80 → 主升。"""
        breadth = {
            "limit_up_count": 100,
            "limit_down_count": 5,
            "continuous_limit_height": 6,
            "broken_limit_rate": 10,
            "up_ratio": 3.0,
        }
        state = get_market_state(breadth)
        assert state["state"] == "主升"

    def test_medium_limit_up_oscillate(self):
        """涨停 20-80 → 震荡。"""
        breadth = {
            "limit_up_count": 50,
            "limit_down_count": 10,
            "continuous_limit_height": 3,
            "broken_limit_rate": 20,
            "up_ratio": 1.5,
        }
        state = get_market_state(breadth)
        assert state["state"] == "震荡"

    def test_extreme_limit_down_freeze(self):
        """跌停 > 50 → 冰点。"""
        breadth = {
            "limit_up_count": 5,
            "limit_down_count": 60,
            "continuous_limit_height": 1,
            "broken_limit_rate": 50,
            "up_ratio": 0.3,
        }
        state = get_market_state(breadth)
        assert state["state"] == "冰点"

    def test_high_limit_down_retreat(self):
        """跌停 > 30 且原状态为震荡 → 退潮。"""
        breadth = {
            "limit_up_count": 50,
            "limit_down_count": 40,
            "continuous_limit_height": 2,
            "broken_limit_rate": 30,
            "up_ratio": 1.0,
        }
        state = get_market_state(breadth)
        assert state["state"] == "退潮"

    def test_continuous_height_signal(self):
        """连板高度 >= 5 产生信号。"""
        breadth = {
            "limit_up_count": 50,
            "limit_down_count": 5,
            "continuous_limit_height": 5,
            "broken_limit_rate": 10,
            "up_ratio": 1.5,
        }
        state = get_market_state(breadth)
        assert any("连板高度5板" in s for s in state["signals"])

    def test_low_continuous_height_signal(self):
        """连板高度 <= 2 产生信号。"""
        breadth = {
            "limit_up_count": 50,
            "limit_down_count": 5,
            "continuous_limit_height": 1,
            "broken_limit_rate": 10,
            "up_ratio": 1.5,
        }
        state = get_market_state(breadth)
        assert any("接力生态恶化" in s for s in state["signals"])

    def test_high_broken_rate_signal(self):
        """炸板率 > 40% 产生信号。"""
        breadth = {
            "limit_up_count": 50,
            "limit_down_count": 5,
            "continuous_limit_height": 3,
            "broken_limit_rate": 50,
            "up_ratio": 1.5,
        }
        state = get_market_state(breadth)
        assert any("炸板率" in s for s in state["signals"])

    def test_up_ratio_high(self):
        """涨跌比 > 2 → 市场普涨。"""
        breadth = {
            "limit_up_count": 50,
            "limit_down_count": 5,
            "continuous_limit_height": 3,
            "broken_limit_rate": 10,
            "up_ratio": 3.0,
        }
        state = get_market_state(breadth)
        assert any("普涨" in s for s in state["signals"])

    def test_up_ratio_low(self):
        """涨跌比 < 0.5 → 市场普跌。"""
        breadth = {
            "limit_up_count": 10,
            "limit_down_count": 5,
            "continuous_limit_height": 3,
            "broken_limit_rate": 10,
            "up_ratio": 0.3,
        }
        state = get_market_state(breadth)
        assert any("普跌" in s for s in state["signals"])

    def test_confidence_freeze(self):
        """冰点 → 高置信度。"""
        breadth = {
            "limit_up_count": 5,
            "limit_down_count": 60,
            "continuous_limit_height": 1,
            "broken_limit_rate": 50,
            "up_ratio": 0.3,
        }
        state = get_market_state(breadth)
        assert state["confidence"] == "高"

    def test_confidence_medium(self):
        """退潮/主升 → 中置信度。"""
        breadth = {
            "limit_up_count": 10,
            "limit_down_count": 5,
            "continuous_limit_height": 3,
            "broken_limit_rate": 20,
            "up_ratio": 1.0,
        }
        state = get_market_state(breadth)
        assert state["confidence"] == "中"

    def test_confidence_low(self):
        """震荡 → 低置信度。"""
        breadth = {
            "limit_up_count": 50,
            "limit_down_count": 10,
            "continuous_limit_height": 3,
            "broken_limit_rate": 20,
            "up_ratio": 1.5,
        }
        state = get_market_state(breadth)
        assert state["confidence"] == "低"


class TestFormatBreadth:
    """format_breadth 格式化输出。"""

    def test_contains_header(self):
        breadth = _default_result()
        state = {"state": "震荡", "confidence": "低", "signals": ["信号1"]}
        result = format_breadth(breadth, state)
        assert "市场宽度分析" in result

    def test_contains_limit_data(self):
        breadth = {
            "limit_up_count": 50,
            "limit_down_count": 10,
            "continuous_limit_height": 3,
            "broken_limit_rate": 20,
            "total_stocks": 5000,
            "up_count": 2500,
            "down_count": 2000,
            "up_ratio": 1.25,
        }
        state = {"state": "震荡", "confidence": "低", "signals": ["信号1"]}
        result = format_breadth(breadth, state)
        assert "50" in result
        assert "10" in result
        assert "1.25" in result

    def test_contains_signals(self):
        breadth = _default_result()
        state = {
            "state": "震荡",
            "confidence": "低",
            "signals": ["涨停家数50家", "涨跌比1.5"],
        }
        result = format_breadth(breadth, state)
        assert "涨停家数50家" in result
        assert "涨跌比1.5" in result
