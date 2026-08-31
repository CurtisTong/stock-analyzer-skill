"""_find_swing_points 确认延迟（confirm）与 past-only（confirm=False）测试。"""

from __future__ import annotations

from technical.core import _find_swing_points


class TestConfirm:
    def test_confirm_true_skips_recent_window(self):
        """confirm=True：最近 window 根不标记（确认延迟）。"""
        values = [1, 5, 3, 4, 2, 6, 3, 2, 1, 0]
        highs, lows = _find_swing_points(values, window=2, confirm=True)
        # 极值应 ≤ len - window - 1
        assert all(h <= len(values) - 2 - 1 for h in highs)

    def test_confirm_true_detects_mid_peak(self):
        values = [1, 2, 5, 3, 1, 2]
        highs, _ = _find_swing_points(values, window=2, confirm=True)
        assert 2 in highs  # index 2 = 5 是峰值

    def test_past_only_immediate_detection(self):
        """confirm=False：最近 window 根立即参与（尾部新高低点被标记）。"""
        values = [1, 2, 3, 2, 1, 8]  # 最后 8 是尚未确认的新高
        highs, _ = _find_swing_points(values, window=2, confirm=False)
        assert 5 in highs  # index 5 = 8 立即标记

    def test_past_only_with_confirm_same_mid(self):
        """中部极值在两种模式下都应被识别。"""
        values = [1, 2, 5, 3, 1, 2]
        h1, _ = _find_swing_points(values, window=2, confirm=True)
        h2, _ = _find_swing_points(values, window=2, confirm=False)
        assert 2 in h1 and 2 in h2

    def test_too_short_returns_empty(self):
        assert _find_swing_points([1, 2], window=5) == ([], [])
        assert _find_swing_points([1, 2], window=5, confirm=False) == ([], [])

    def test_monotonic_down_no_false_highs(self):
        """单调下跌不应标记摆动高点（修复：confirm 覆写左窗口产生 90 个假高点）。"""
        highs, lows = _find_swing_points(list(range(100, 0, -1)), window=5)
        assert highs == []  # 修复前：90 个假高点
        assert lows == []

    def test_monotonic_up_no_false_lows(self):
        """单调上涨不应标记摆动低点。"""
        highs, lows = _find_swing_points(list(range(1, 101)), window=5)
        assert highs == []
        assert lows == []  # 修复前：90 个假低点

    def test_swing_requires_both_windows(self):
        """摆动点须左右窗口同时确认（修复：仅右窗口不构成摆动点）。"""
        # 中部峰值 5 两侧都是低值 → 是摆动高点
        values = [1, 2, 5, 3, 1, 2]
        highs, _ = _find_swing_points(values, window=2, confirm=True)
        assert 2 in highs
        # 斜坡（每个点都比右侧高但左侧更高）→ 不是摆动高点
        ramp = [10, 9, 8, 7, 6, 5, 4, 3]
        highs2, _ = _find_swing_points(ramp, window=2, confirm=True)
        assert highs2 == []
