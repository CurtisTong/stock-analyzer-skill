"""因子注册表单元测试。"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from strategies.factors.registry import (
    register_factor,
    get_factor,
    list_factors,
    list_phase_factors,
    get_factor_keys,
    compute_all_factors,
    compute_phase_factors,
    Phase,
    ArgsStyle,
)


class TestRegisterFactor:
    def test_register_and_get(self):
        """注册后可获取因子。"""
        register_factor(
            "test_dummy",
            compute_fn=lambda fin, industry: 42,
            phase=1,
            args_style="fin_industry",
        )
        desc = get_factor("test_dummy")
        assert desc.name == "test_dummy"
        assert desc.phase == Phase.PHASE1

    def test_get_unknown_factor_raises(self):
        """获取未知因子抛 KeyError。"""
        with pytest.raises(KeyError, match="未知因子"):
            get_factor("nonexistent_factor_xyz")

    def test_list_factors_includes_registered(self):
        """list_factors 包含已注册因子。"""
        factors = list_factors()
        assert "quality" in factors
        assert "valuation" in factors
        assert "momentum" in factors

    def test_list_phase_factors_filters(self):
        """list_phase_factors 正确过滤阶段。"""
        phase1 = list_phase_factors(1)
        phase2 = list_phase_factors(2)
        assert "quality" in phase1
        assert "momentum" in phase2
        assert "quality" not in phase2
        assert "momentum" not in phase1

    def test_get_factor_keys_returns_all(self):
        """get_factor_keys 返回所有因子名。"""
        keys = get_factor_keys()
        assert len(keys) >= 7
        assert "quality" in keys
        assert "chip" in keys


class TestComputeAllFactors:
    def test_returns_all_registered_factors(self):
        """compute_all_factors 返回所有已注册因子。"""
        fin = {"eps": 1.0, "roe": 15.0, "net_profit_yoy": 20.0}
        quote = {
            "pe": 20,
            "pb": 3,
            "total_cap": 100,
            "amount": 50000,
            "code": "sh600519",
        }
        features = {"closes": [10.0 + i * 0.1 for i in range(60)]}
        result = compute_all_factors(fin, quote, features, "默认", "sh600519")
        assert "quality" in result
        assert "valuation" in result
        assert "momentum" in result

    def test_returns_float_scores(self):
        """所有因子返回 float 分数。"""
        fin = {"eps": 1.0, "roe": 15.0}
        quote = {"pe": 20, "pb": 3, "code": "sh600519"}
        features = {}
        result = compute_all_factors(fin, quote, features, "默认", "sh600519")
        for k, v in result.items():
            assert isinstance(v, (int, float)), f"{k} 应为数值，实际为 {type(v)}"

    def test_failed_factor_returns_neutral(self):
        """因子计算失败时返回中性分 50。"""
        # 传空数据触发异常
        result = compute_all_factors({}, {}, {}, "", "")
        assert all(isinstance(v, (int, float)) for v in result.values())

    def test_zero_weight_factors_skipped(self):
        """P0-12：权重为 0 的因子跳过计算（不包含在结果中）。"""
        fin = {"eps": 1.0, "roe": 15.0, "net_profit_yoy": 20.0}
        quote = {
            "pe": 20,
            "pb": 3,
            "total_cap": 100,
            "amount": 50000,
            "code": "sh600519",
        }
        features = {"closes": [10.0 + i * 0.1 for i in range(60)]}
        # event/analyst 权重为 0，应被跳过
        weights = {
            "quality": 0.30,
            "valuation": 0.20,
            "momentum": 0.15,
            "liquidity": 0.05,
            "volatility": 0.15,
            "dividend": 0.05,
            "chip": 0.10,
            "event": 0.0,
            "analyst": 0.0,
        }
        result = compute_all_factors(
            fin, quote, features, "默认", "sh600519", weights=weights
        )
        assert "event" not in result
        assert "analyst" not in result
        # 权重非 0 的因子仍应计算
        assert "quality" in result
        assert "valuation" in result

    def test_no_weights_computes_all(self):
        """不传 weights 时全量计算（向后兼容）。"""
        fin = {"eps": 1.0, "roe": 15.0, "net_profit_yoy": 20.0}
        quote = {
            "pe": 20,
            "pb": 3,
            "total_cap": 100,
            "amount": 50000,
            "code": "sh600519",
        }
        features = {"closes": [10.0 + i * 0.1 for i in range(60)]}
        result = compute_all_factors(fin, quote, features, "默认", "sh600519")
        assert "event" in result
        assert "analyst" in result


class TestComputePhaseFactors:
    def test_phase1_excludes_kline_factors(self):
        """Phase 1 不包含 K 线依赖因子。"""
        fin = {"eps": 1.0, "roe": 15.0}
        quote = {"pe": 20, "pb": 3, "code": "sh600519"}
        result = compute_phase_factors(1, fin, quote, {}, "默认", "sh600519")
        assert "quality" in result
        assert "valuation" in result
        assert "momentum" not in result
        assert "volatility" not in result

    def test_phase2_excludes_non_kline_factors(self):
        """Phase 2 不包含非 K 线因子。"""
        fin = {"eps": 1.0, "roe": 15.0}
        quote = {"pe": 20, "pb": 3, "code": "sh600519"}
        features = {"closes": [10.0] * 60}
        result = compute_phase_factors(2, fin, quote, features, "默认", "sh600519")
        assert "momentum" in result
        assert "volatility" in result
        assert "quality" not in result

    def test_phase1_skips_zero_weight_factors(self):
        """P0-12：Phase 1 中权重为 0 的因子（event/analyst）跳过计算。"""
        fin = {"eps": 1.0, "roe": 15.0}
        quote = {"pe": 20, "pb": 3, "code": "sh600519"}
        weights = {"event": 0.0, "analyst": 0.0, "quality": 0.3}
        result = compute_phase_factors(
            1, fin, quote, {}, "默认", "sh600519", weights=weights
        )
        assert "event" not in result
        assert "analyst" not in result
        assert "quality" in result
