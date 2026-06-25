"""市场状态 overlay 权重调节测试。"""

import pytest
from strategies.regime.classifier import RegimeState
from strategies.regime.overlay import OVERLAY_MATRIX, compute_overlay_weights


class TestOverlayMatrix:
    """OVERLAY_MATRIX 矩阵完整性。"""

    def test_all_regimes_covered(self):
        """4 种市场状态都有对应权重。"""
        for state in RegimeState:
            assert state in OVERLAY_MATRIX

    def test_all_factors_covered(self):
        """每个状态都包含 9 个因子。"""
        expected = {
            "quality",
            "valuation",
            "momentum",
            "liquidity",
            "volatility",
            "dividend",
            "chip",
            "event",
            "analyst",
        }
        for state, weights in OVERLAY_MATRIX.items():
            assert set(weights.keys()) == expected

    def test_bull_momentum_boost(self):
        """牛市动量 +30%。"""
        assert OVERLAY_MATRIX[RegimeState.BULL]["momentum"] == 1.3

    def test_bear_quality_boost(self):
        """熊市质量 +20%。"""
        assert OVERLAY_MATRIX[RegimeState.BEAR]["quality"] == 1.2

    def test_panic_momentum_slash(self):
        """冰点动量 -50%。"""
        assert OVERLAY_MATRIX[RegimeState.PANIC]["momentum"] == 0.5

    def test_panic_quality_boost(self):
        """冰点质量 +30%。"""
        assert OVERLAY_MATRIX[RegimeState.PANIC]["quality"] == 1.3


class TestComputeOverlayWeights:
    """compute_overlay_weights 权重调节。"""

    def _equal_weights(self):
        """6 因子等权重。"""
        return {
            k: 1 / 6
            for k in (
                "quality",
                "valuation",
                "momentum",
                "liquidity",
                "volatility",
                "dividend",
            )
        }

    def test_bull_sum_to_one(self):
        """牛市调节后权重总和 = 1.0。"""
        result = compute_overlay_weights(self._equal_weights(), RegimeState.BULL)
        assert abs(sum(result.values()) - 1.0) < 1e-4

    def test_bear_sum_to_one(self):
        """熊市调节后权重总和 = 1.0。"""
        result = compute_overlay_weights(self._equal_weights(), RegimeState.BEAR)
        assert abs(sum(result.values()) - 1.0) < 1e-4

    def test_range_sum_to_one(self):
        """震荡调节后权重总和 = 1.0。"""
        result = compute_overlay_weights(self._equal_weights(), RegimeState.RANGE)
        assert abs(sum(result.values()) - 1.0) < 1e-4

    def test_panic_sum_to_one(self):
        """冰点调节后权重总和 = 1.0。"""
        result = compute_overlay_weights(self._equal_weights(), RegimeState.PANIC)
        assert abs(sum(result.values()) - 1.0) < 1e-4

    def test_bull_momentum_increases(self):
        """牛市动量权重应增加。"""
        result = compute_overlay_weights(self._equal_weights(), RegimeState.BULL)
        # 等权重时动量 1/6 ≈ 0.1667，调节后应更大
        assert result["momentum"] > 1 / 6

    def test_bear_momentum_decreases(self):
        """熊市动量权重应减少。"""
        result = compute_overlay_weights(self._equal_weights(), RegimeState.BEAR)
        assert result["momentum"] < 1 / 6

    def test_panic_quality_dominates(self):
        """冰点质量权重应最高。"""
        result = compute_overlay_weights(self._equal_weights(), RegimeState.PANIC)
        assert result["quality"] == max(result.values())

    def test_skips_label_key(self):
        """跳过 label 和 two_stage 键。"""
        weights = {**self._equal_weights(), "label": "balanced", "two_stage": False}
        result = compute_overlay_weights(weights, RegimeState.BULL)
        assert "label" not in result
        assert "two_stage" not in result

    def test_zero_total_returns_original(self):
        """全零权重返回原始权重。"""
        zero_weights = {
            k: 0
            for k in (
                "quality",
                "valuation",
                "momentum",
                "liquidity",
                "volatility",
                "dividend",
            )
        }
        result = compute_overlay_weights(zero_weights, RegimeState.BULL)
        assert result == zero_weights

    def test_custom_weights(self):
        """自定义权重也能正确归一化。"""
        custom = {"quality": 0.4, "valuation": 0.3, "momentum": 0.2, "liquidity": 0.1}
        result = compute_overlay_weights(custom, RegimeState.BULL)
        assert abs(sum(result.values()) - 1.0) < 1e-4
