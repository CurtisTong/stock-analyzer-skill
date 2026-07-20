"""
scripts/strategies/registry.py 的单元测试。

按 FRAMEWORK.md 规范：
- 测试类 TestXxxYyy（语义唯一）
- 测试方法 test_行为_期望
- parametrize 优先
- 无 mock IO（dict + threading.RLock 是纯内存）
- 无 sys.path.insert（依赖 pyproject.toml::pythonpath）

覆盖：
- 6 个内置策略的结构完整性（权重和 = 1.0、必需因子存在）
- register_strategy / get_strategy / list_strategies / strategy_exists
- 错误路径：缺必需键、权重和偏离、重复注册
- replace=True 覆盖行为
- 多线程并发注册安全性
"""

from __future__ import annotations

import threading

import pytest

from strategies import registry
from strategies.registry import (
    STRATEGIES,
    get_strategy,
    list_strategies,
    register_strategy,
    strategy_exists,
)


@pytest.fixture(autouse=True)
def _isolate_registry():
    """每个测试前快照 STRATEGIES，测试后恢复，避免污染全局状态。"""
    snapshot = {k: dict(v) for k, v in STRATEGIES.items()}
    yield
    STRATEGIES.clear()
    STRATEGIES.update(snapshot)


# ═══════════════════════════════════════════════════════════════
# 内置策略结构完整性
# ═══════════════════════════════════════════════════════════════


class TestBuiltinStrategies:
    """验证 6 个内置策略的结构完整性（防御漂移）。"""

    REQUIRED_KEYS = {
        "quality",
        "valuation",
        "momentum",
        "liquidity",
    }
    OPTIONAL_KEYS = {
        "volatility",
        "dividend",
        "chip",
        "event",
        "analyst",
    }
    EXPECTED_STRATEGIES = {
        "balanced",
        "quality_value",
        "growth_momentum",
        "defensive",
        "turning_point",
        "ma_volume_momentum",
    }

    def test_six_builtin_strategies_present(self):
        """6 个内置策略必须存在。"""
        assert set(STRATEGIES.keys()) == self.EXPECTED_STRATEGIES

    @pytest.mark.parametrize("name", sorted(EXPECTED_STRATEGIES))
    def test_each_strategy_has_required_keys(self, name):
        """每个策略必须含必需键（quality/valuation/momentum/liquidity）。"""
        strategy = STRATEGIES[name]
        missing = self.REQUIRED_KEYS - strategy.keys()
        assert not missing, f"{name} 缺少必需键: {missing}"

    @pytest.mark.parametrize("name", sorted(EXPECTED_STRATEGIES))
    def test_each_strategy_weights_sum_to_one(self, name):
        """每个策略的因子权重之和应在 1.0 ± 0.01 范围内。"""
        strategy = STRATEGIES[name]
        all_keys = self.REQUIRED_KEYS | self.OPTIONAL_KEYS
        total = sum(strategy.get(k, 0) for k in all_keys)
        assert abs(total - 1.0) <= 0.01, f"{name} 权重和为 {total}，应在 1.0 ± 0.01"

    @pytest.mark.parametrize("name", sorted(EXPECTED_STRATEGIES))
    def test_each_strategy_has_label(self, name):
        """每个策略必须含中文 label。"""
        assert "label" in STRATEGIES[name], f"{name} 缺少 label"
        assert STRATEGIES[name]["label"], f"{name} label 为空"

    def test_turning_point_has_two_stage_marker(self):
        """turning_point 是双阶段策略，必须有 two_stage=True 标记。"""
        assert STRATEGIES["turning_point"].get("two_stage") is True

    def test_weights_non_negative(self):
        """所有权重应非负（空仓/防御允许 0，但不允许负数）。"""
        for name, strategy in STRATEGIES.items():
            for k, v in strategy.items():
                if k in self.REQUIRED_KEYS | self.OPTIONAL_KEYS:
                    assert v >= 0, f"{name}.{k} = {v} 为负"


# ═══════════════════════════════════════════════════════════════
# get_strategy / list_strategies / strategy_exists
# ═══════════════════════════════════════════════════════════════


class TestGetStrategy:
    def test_existing_strategy(self):
        s = get_strategy("balanced")
        assert s["label"] == "均衡精选"
        assert s["quality"] == 0.28

    def test_unknown_strategy_raises(self):
        with pytest.raises(KeyError, match="未知策略"):
            get_strategy("not_a_strategy")


class TestListStrategies:
    def test_returns_six_builtins(self):
        names = list_strategies()
        assert len(names) == 6
        assert "balanced" in names
        assert "turning_point" in names

    def test_returns_list_type(self):
        assert isinstance(list_strategies(), list)


class TestStrategyExists:
    @pytest.mark.parametrize("name", ["balanced", "quality_value", "growth_momentum"])
    def test_existing(self, name):
        assert strategy_exists(name) is True

    @pytest.mark.parametrize("name", ["", "unknown", "BALANCED"])
    def test_missing(self, name):
        assert strategy_exists(name) is False


# ═══════════════════════════════════════════════════════════════
# register_strategy
# ═══════════════════════════════════════════════════════════════


class TestRegisterStrategy:
    """注册新策略 + 各种校验路径。"""

    def _valid_weights(self) -> dict:
        return {
            "quality": 0.25,
            "valuation": 0.25,
            "momentum": 0.25,
            "liquidity": 0.25,
        }

    def test_register_new_strategy(self):
        register_strategy("custom_test", self._valid_weights(), label="测试")
        assert strategy_exists("custom_test")
        assert get_strategy("custom_test")["label"] == "测试"

    def test_register_with_optional_keys(self):
        weights = {
            "quality": 0.30,
            "valuation": 0.20,
            "momentum": 0.20,
            "liquidity": 0.10,
            "volatility": 0.10,
            "dividend": 0.10,
        }
        register_strategy("custom_v2", weights, label="带可选键")
        # 缺省的 chip/event/analyst 应自动补 0
        s = get_strategy("custom_v2")
        assert s["chip"] == 0.0
        assert s["event"] == 0.0
        assert s["analyst"] == 0.0

    def test_missing_required_keys_raises(self):
        weights = {"quality": 0.5, "valuation": 0.5}  # 缺 momentum/liquidity
        with pytest.raises(ValueError, match="必须包含"):
            register_strategy("incomplete", weights)

    def test_weights_sum_not_one_raises(self):
        weights = {
            "quality": 0.5,
            "valuation": 0.3,
            "momentum": 0.1,  # 和 = 0.9
            "liquidity": 0.0,
        }
        with pytest.raises(ValueError, match="权重之和应为 1.0"):
            register_strategy("bad_sum", weights)

    def test_duplicate_registration_protected(self):
        """重复注册应抛错（保护全局状态不被并发修改）。"""
        with pytest.raises(ValueError, match="已注册"):
            register_strategy("balanced", self._valid_weights())

    def test_replace_true_overrides_existing(self):
        """replace=True 可覆盖已有策略。"""
        register_strategy(
            "balanced", self._valid_weights(), label="覆盖测试", replace=True
        )
        assert get_strategy("balanced")["label"] == "覆盖测试"

    def test_label_defaults_to_name(self):
        """label 缺省时回退到策略 name。"""
        register_strategy("no_label", self._valid_weights())
        assert get_strategy("no_label")["label"] == "no_label"

    def test_register_does_not_mutate_input(self):
        """register_strategy 不应修改入参 weights。"""
        weights = self._valid_weights()
        snapshot = dict(weights)
        register_strategy("pure_test", weights, label="不修改入参")
        assert weights == snapshot


# ═══════════════════════════════════════════════════════════════
# 并发安全
# ═══════════════════════════════════════════════════════════════


class TestConcurrencySafety:
    """RLock 应保护 STRATEGIES 写入，并发注册同名应只剩一个赢家。"""

    def test_concurrent_register_different_names(self):
        """并发注册不同名称的策略。"""
        errors: list = []

        def register_one(name: str):
            try:
                register_strategy(
                    f"thread_{name}",
                    {
                        "quality": 0.25,
                        "valuation": 0.25,
                        "momentum": 0.25,
                        "liquidity": 0.25,
                    },
                )
            except ValueError as e:
                errors.append(e)

        threads = [
            threading.Thread(target=register_one, args=(str(i),)) for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"并发注册失败: {errors}"
        for i in range(10):
            assert strategy_exists(f"thread_{i}")

    def test_concurrent_read_under_register(self):
        """注册期间并发读取不应崩溃。"""
        errors: list = []

        def reader():
            try:
                for _ in range(100):
                    list_strategies()
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                register_strategy(
                    "rw_test",
                    {
                        "quality": 0.25,
                        "valuation": 0.25,
                        "momentum": 0.25,
                        "liquidity": 0.25,
                    },
                )
            except ValueError:
                pass  # 可能被其他线程抢先注册

        threads = [threading.Thread(target=reader) for _ in range(5)] + [
            threading.Thread(target=writer)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"并发读取失败: {errors}"
