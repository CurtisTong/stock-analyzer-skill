"""竹节法卖点识别单元测试。

覆盖场景：
- 走弱（最高价未创新高）-> signal=-1
- 转势（最低价创新低）-> signal=-2（优先级高于走弱）
- 维持（高低阶梯抬升）-> signal=0
- 数据不足 -> None
"""

import pytest

from technical.bamboo import bamboo_node


def _seq(base, steps):
    """生成单调序列：base 起始，steps 为每日增量。"""
    vals = []
    v = base
    for s in steps:
        v = round(v + s, 2)
        vals.append(v)
    return vals


class TestBambooNode:
    """竹节法识别。"""

    def test_weak_high_not_new_high(self):
        """最高价未创新高 -> 走弱减仓信号。"""
        # 前5日高点持续抬升，今日高点回落
        highs = [10.0, 10.5, 11.0, 11.5, 12.0, 11.8]
        lows = [9.0, 9.5, 10.0, 10.5, 11.0, 11.2]
        closes = [9.5, 10.0, 10.5, 11.0, 11.5, 11.5]
        result = bamboo_node(highs, lows, closes)
        assert result is not None
        assert result["signal"] == -1
        assert "走弱" in result["status"]

    def test_reversal_low_new_low(self):
        """最低价创新低 -> 转势清仓信号（优先级高于走弱）。"""
        # 今日最高未创新高 + 今日最低创新低
        highs = [10.0, 10.5, 11.0, 11.5, 12.0, 11.8]
        lows = [9.0, 9.5, 10.0, 10.5, 11.0, 8.8]
        closes = [9.5, 10.0, 10.5, 11.0, 11.5, 9.0]
        result = bamboo_node(highs, lows, closes)
        assert result is not None
        assert result["signal"] == -2
        assert "转势" in result["status"]

    def test_maintain_staircase_rising(self):
        """高低阶梯抬升 -> 维持（signal=0）。"""
        highs = [10.0, 10.5, 11.0, 11.5, 12.0, 12.5]
        lows = [9.0, 9.5, 10.0, 10.5, 11.0, 11.2]
        closes = [9.5, 10.0, 10.5, 11.0, 11.5, 12.0]
        result = bamboo_node(highs, lows, closes)
        assert result is not None
        assert result["signal"] == 0
        assert "维持" in result["status"]

    def test_reversal_overrides_weak(self):
        """转势优先级高于走弱：同时满足时返回 -2。"""
        # 今日最高未创新高 AND 今日最低创新低
        highs = [10.0, 10.5, 11.0, 11.5, 12.0, 11.9]
        lows = [9.0, 9.5, 10.0, 10.5, 11.0, 8.5]
        closes = [9.5, 10.0, 10.5, 11.0, 11.5, 9.0]
        result = bamboo_node(highs, lows, closes)
        assert result["signal"] == -2

    def test_insufficient_data_returns_none(self):
        """数据不足返回 None。"""
        highs = [10.0, 10.5, 11.0]
        lows = [9.0, 9.5, 10.0]
        closes = [9.5, 10.0, 10.5]
        assert bamboo_node(highs, lows, closes) is None

    def test_return_structure_fields(self):
        """返回 dict 包含所有约定字段。"""
        highs = [10.0, 10.5, 11.0, 11.5, 12.0, 11.8]
        lows = [9.0, 9.5, 10.0, 10.5, 11.0, 11.2]
        closes = [9.5, 10.0, 10.5, 11.0, 11.5, 11.5]
        result = bamboo_node(highs, lows, closes)
        for key in (
            "status",
            "signal",
            "desc",
            "prev_high",
            "prev_low",
            "today_high",
            "today_low",
        ):
            assert key in result, f"缺少字段 {key}"

    def test_custom_window(self):
        """自定义窗口生效。"""
        # window=3，前3日最高12.0，今日11.8未创新高
        highs = [10.0, 11.0, 12.0, 11.8]
        lows = [9.0, 10.0, 11.0, 11.2]
        closes = [9.5, 10.5, 11.5, 11.5]
        result = bamboo_node(highs, lows, closes, window=3)
        assert result is not None
        assert result["signal"] == -1
