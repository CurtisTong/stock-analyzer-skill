"""
策略注册表覆盖率测试（Sprint 11）。
"""

import pytest

from strategies import registry


class TestRegisterStrategy:
    """register_strategy 边界测试。"""

    def test_register_with_full_weights(self):
        """完整 6 因子权重可注册。"""
        original_count = len(registry.STRATEGIES)
        registry.register_strategy(
            "test_full",
            {
                "quality": 0.3,
                "valuation": 0.2,
                "momentum": 0.2,
                "liquidity": 0.1,
                "volatility": 0.1,
                "dividend": 0.1,
            },
            label="完整测试",
        )
        assert "test_full" in registry.STRATEGIES
        assert registry.STRATEGIES["test_full"]["label"] == "完整测试"
        # 清理
        del registry.STRATEGIES["test_full"]
        assert len(registry.STRATEGIES) == original_count

    def test_register_missing_required_key_raises(self):
        """缺必需因子（quality/valuation/momentum/liquidity）应抛 ValueError。"""
        with pytest.raises(ValueError, match="必须包含"):
            registry.register_strategy("test_bad", {"quality": 1.0})  # 只 1 个

    def test_register_invalid_weight_sum_raises(self):
        """权重和 != 1.0 应抛 ValueError。"""
        with pytest.raises(ValueError, match="权重之和"):
            registry.register_strategy(
                "test_sum",
                {
                    "quality": 0.5,
                    "valuation": 0.5,
                    "momentum": 0.5,
                    "liquidity": 0.5,  # 总和 2.0
                },
            )

    def test_register_missing_optional_filled_zero(self):
        """缺可选因子（volatility/dividend）应补 0。"""
        registry.register_strategy(
            "test_optional",
            {
                "quality": 0.3,
                "valuation": 0.3,
                "momentum": 0.2,
                "liquidity": 0.2,  # 总和 1.0
            },
        )
        assert registry.STRATEGIES["test_optional"]["volatility"] == 0.0
        assert registry.STRATEGIES["test_optional"]["dividend"] == 0.0
        del registry.STRATEGIES["test_optional"]


class TestGetStrategy:
    """get_strategy 测试。"""

    def test_get_builtin_strategy(self):
        """获取内置策略。"""
        cfg = registry.get_strategy("balanced")
        assert "quality" in cfg
        assert cfg["label"] == "均衡精选"

    def test_get_unknown_raises(self):
        """未知策略名应抛 KeyError。"""
        with pytest.raises(KeyError, match="未知策略"):
            registry.get_strategy("nonexistent_strategy_xyz")


class TestListStrategies:
    """list_strategies 测试。"""

    def test_returns_all_builtin(self):
        """返回 6 个内置策略。"""
        names = registry.list_strategies()
        assert set(names) == {
            "balanced",
            "quality_value",
            "growth_momentum",
            "defensive",
            "turning_point",
            "ma_volume_momentum",
        }
