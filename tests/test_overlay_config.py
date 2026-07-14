"""(#7) OVERLAY 配置外置 + 策略混合测试。

覆盖：
- 配置文件存在时读取 multiplier
- 配置文件缺失时回退硬编码
- 策略混合（BEAR 时 balanced:0.7 + defensive:0.3）
- 归一化不变性
- get_overlay_matrix / get_strategy_blend 独立可测
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from strategies.regime.overlay import (  # noqa: E402
    _HARDCODED_MATRIX,
    _HARDCODED_BLEND,
    get_overlay_matrix,
    get_strategy_blend,
    compute_overlay_weights,
)
from strategies.regime import RegimeState  # noqa: E402


class TestOverlayConfigLoad:
    """配置加载与回退。"""

    def test_config_exists_returns_configured_matrix(self):
        """配置文件存在时返回配置值（regime_weight_map.yaml 已创建）。"""
        matrix = get_overlay_matrix()
        # 4 状态都应存在
        for state in RegimeState:
            assert state in matrix
        # BULL momentum 应为 1.3（配置值）
        assert matrix[RegimeState.BULL]["momentum"] == 1.3

    def test_config_missing_falls_back_to_hardcoded(self):
        """配置文件缺失时回退硬编码。"""
        with patch("strategies.regime.overlay._load_config", return_value={}):
            matrix = get_overlay_matrix()
        assert matrix == _HARDCODED_MATRIX

    def test_config_partial_state_uses_hardcoded_for_missing(self):
        """配置只覆盖部分状态时，缺失状态用硬编码。"""
        partial = {"BULL": {"momentum": 1.5}}  # 只有 BULL
        with patch("strategies.regime.overlay._load_config", return_value=partial):
            matrix = get_overlay_matrix()
        # BULL 用配置值
        assert matrix[RegimeState.BULL]["momentum"] == 1.5
        # BEAR 用硬编码
        assert matrix[RegimeState.BEAR]["momentum"] == 0.7

    def test_config_partial_factor_uses_hardcoded_for_missing(self):
        """配置只覆盖部分因子时，缺失因子用硬编码。"""
        partial = {"BULL": {"momentum": 2.0}}
        with patch("strategies.regime.overlay._load_config", return_value=partial):
            matrix = get_overlay_matrix()
        # momentum 用配置
        assert matrix[RegimeState.BULL]["momentum"] == 2.0
        # quality 用硬编码
        assert matrix[RegimeState.BULL]["quality"] == 1.0


class TestStrategyBlend:
    """策略混合规则。"""

    def test_blend_config_exists(self):
        """配置文件存在时返回配置的 blend 规则。"""
        blend = get_strategy_blend()
        # BEAR 应有 balanced:0.7 + defensive:0.3
        assert RegimeState.BEAR in blend
        assert blend[RegimeState.BEAR].get("balanced") == 0.7
        assert blend[RegimeState.BEAR].get("defensive") == 0.3

    def test_blend_missing_config_falls_back(self):
        """配置缺失时回退硬编码 blend。"""
        with patch("strategies.regime.overlay._load_config", return_value={}):
            blend = get_strategy_blend()
        assert blend == _HARDCODED_BLEND

    def test_blend_not_applied_without_label(self):
        """无 label 字段的权重不触发混合（纯因子 dict）。"""
        weights = {
            "quality": 0.30,
            "valuation": 0.20,
            "momentum": 0.20,
        }
        out = compute_overlay_weights(weights, RegimeState.BEAR)
        # 无 label -> 不混合，仅 overlay
        assert abs(sum(out.values()) - 1.0) < 0.001

    def test_blend_applied_for_balanced_in_bear(self):
        """balanced 策略在 BEAR 时混合 defensive。"""
        from strategies import get_strategy

        weights = get_strategy("balanced")
        out = compute_overlay_weights(weights, RegimeState.BEAR)

        # 混合后应包含所有因子
        assert "quality" in out
        assert "volatility" in out
        # 归一化
        assert abs(sum(out.values()) - 1.0) < 0.001

    def test_blend_not_applied_for_unmatched_strategy(self):
        """策略名不在 blend 规则中时不混合（如 RANGE 下无 blend）。"""
        from strategies import get_strategy

        weights = get_strategy("balanced")
        # RANGE 无 blend 规则 -> 仅 overlay
        out = compute_overlay_weights(weights, RegimeState.RANGE)
        assert abs(sum(out.values()) - 1.0) < 0.001


class TestOverlayNormalization:
    """overlay 后归一化不变性。"""

    @pytest.mark.parametrize("state", list(RegimeState))
    def test_all_states_normalize_to_one(self, state):
        """所有状态 overlay 后权重和 = 1.0。"""
        from strategies import get_strategy

        weights = get_strategy("balanced")
        out = compute_overlay_weights(weights, state)
        assert abs(sum(out.values()) - 1.0) < 0.001

    def test_overlay_preserves_positive_weights(self):
        """overlay 后非零权重的因子保持正值（0 权重因子不变）。"""
        from strategies import get_strategy

        weights = get_strategy("balanced")
        for state in RegimeState:
            out = compute_overlay_weights(weights, state)
            for k, v in out.items():
                if k not in ("label", "two_stage") and weights.get(k, 0) > 0:
                    assert v > 0, f"{state} {k} = {v} 应为正"


class TestOverlayBehavior:
    """overlay 行为不变性（与原硬编码一致）。"""

    def test_bull_increases_momentum(self):
        """bull 状态 momentum 系数 > 1.0。"""
        from strategies import get_strategy

        weights = get_strategy("balanced")
        out = compute_overlay_weights(weights, RegimeState.BULL)
        # momentum 系数 1.3 -> 占比应提升
        assert out["momentum"] > weights["momentum"]

    def test_panic_decreases_momentum(self):
        """panic 状态 momentum 系数 0.5 -> 占比应大幅降低。"""
        from strategies import get_strategy

        weights = get_strategy("balanced")
        out = compute_overlay_weights(weights, RegimeState.PANIC)
        assert out["momentum"] < weights["momentum"]
