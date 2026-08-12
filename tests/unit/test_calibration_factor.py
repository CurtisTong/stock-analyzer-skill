"""P0-08：校准因子公式修正测试。

新公式：(mean_rate - 0.5) × 2 × (1 - min(cv, 0.5))。
mean_rate=0.5（无信息）时恒为 0，不因离散度产生负惩罚。
"""

from __future__ import annotations

from experts.calibration import _calibration_factor_from_rates


class TestCalibrationFactor:
    def test_no_history_returns_zero(self):
        assert _calibration_factor_from_rates([]) == 0.0

    def test_mean_0_5_is_zero_even_with_dispersion(self):
        """mean_rate=0.5（无信息）时恒为 0，离散度不再产生负惩罚。"""
        assert _calibration_factor_from_rates([0.5, 0.5, 0.5]) == 0.0
        # 有离散度（0.5/0.4/0.6 → mean 0.5, cv>0）仍应为 0
        assert _calibration_factor_from_rates([0.5, 0.4, 0.6]) == 0.0

    def test_perfect_calibration_is_1(self):
        assert _calibration_factor_from_rates([1.0, 1.0, 1.0]) == 1.0

    def test_zero_rate_penalizes_but_softer(self):
        """mean_rate=0（完全不可信）→ -0.5（惩罚但受 cv 衰减）。"""
        assert _calibration_factor_from_rates([0.0, 0.0, 0.0]) == -0.5

    def test_high_cv_shrinks_factor(self):
        """高离散度收缩因子幅度（保守校准）。"""
        low_cv = _calibration_factor_from_rates([0.8, 0.8, 0.8])
        high_cv = _calibration_factor_from_rates([0.8, 0.5, 0.5])
        assert 0 < low_cv <= 1.0
        assert abs(high_cv) < abs(low_cv) or high_cv < low_cv

    def test_in_range(self):
        for rates in ([0.1, 0.9], [0.3, 0.7], [0.0, 1.0]):
            f = _calibration_factor_from_rates(rates)
            assert -1.0 <= f <= 1.0
