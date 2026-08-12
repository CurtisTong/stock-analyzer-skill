"""P1-14：_find_swing_points 确认延迟（confirm）与 past-only（confirm=False）测试。"""

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
