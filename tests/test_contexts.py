"""AnalyzeContext + SimContext 边界测试。

验证两个 dataclass 的默认值、必填字段约束、可序列化和可变性。

注意：SimContext 源码实际定义中没有 stop_loss / take_profit 字段，
commission 默认值为 0.00025（非 0.0003）。测试以源码实际行为为准。
"""

import pytest
from dataclasses import asdict, is_dataclass

from business.screening_service import AnalyzeContext
from backtest.engine import SimContext

# ---------- AnalyzeContext ----------


class TestAnalyzeContextDefaults:
    """TC-1: AnalyzeContext 默认值正确。"""

    def test_defaults(self):
        ctx = AnalyzeContext(
            code="sh600519",
            quote={"price": 1500},
            fin_records=[],
            strategy="balanced",
            filters={},
        )

        assert ctx.kline_bars is None
        assert ctx.phase1 is False
        assert ctx.regime == "neutral"
        assert ctx.no_chip is False


class TestAnalyzeContextRequiredFields:
    """TC-2: AnalyzeContext 必填字段缺失 → TypeError。"""

    def test_missing_code_raises_type_error(self):
        with pytest.raises(TypeError):
            AnalyzeContext(
                quote={"price": 1500},
                fin_records=[],
                strategy="balanced",
                filters={},
            )

    def test_missing_quote_raises_type_error(self):
        with pytest.raises(TypeError):
            AnalyzeContext(
                code="sh600519",
                fin_records=[],
                strategy="balanced",
                filters={},
            )

    def test_missing_all_required_raises_type_error(self):
        with pytest.raises(TypeError):
            AnalyzeContext()  # type: ignore[call-arg]


class TestAnalyzeContextAsDict:
    """TC-3: AnalyzeContext 可转为 dict（asdict）。"""

    def test_asdict(self):
        ctx = AnalyzeContext(
            code="sh600519",
            quote={"price": 1500},
            fin_records=[{"eps": 30}],
            strategy="balanced",
            filters={"min_amount": 5000},
            kline_bars=[1, 2, 3],
            phase1=True,
            regime="bull",
            no_chip=True,
        )

        d = asdict(ctx)

        assert d["code"] == "sh600519"
        assert d["quote"] == {"price": 1500}
        assert d["fin_records"] == [{"eps": 30}]
        assert d["strategy"] == "balanced"
        assert d["filters"] == {"min_amount": 5000}
        assert d["kline_bars"] == [1, 2, 3]
        assert d["phase1"] is True
        assert d["regime"] == "bull"
        assert d["no_chip"] is True

    def test_is_dataclass(self):
        assert is_dataclass(AnalyzeContext)


# ---------- SimContext ----------


class TestSimContextDefaults:
    """TC-4: SimContext 默认值。

    源码实际定义（scripts/backtest/engine.py）：
        initial_capital=100000, commission=0.00025, stamp_tax=0.001,
        slippage=0.001, top_n=5, holding_days=5, total_days=60, weights=None

    注意：源码中无 stop_loss / take_profit 字段。
    """

    def test_defaults(self):
        ctx = SimContext(
            strategy_name="balanced",
            codes=["sh600519"],
        )

        assert ctx.initial_capital == 100000
        assert ctx.commission == 0.00025
        assert ctx.stamp_tax == 0.001
        assert ctx.slippage == 0.001
        assert ctx.top_n == 5
        assert ctx.holding_days == 5
        assert ctx.total_days == 60
        assert ctx.weights is None


class TestSimContextRequiredFields:
    """TC-5: SimContext 必填字段缺失 → TypeError。"""

    def test_missing_strategy_name_raises_type_error(self):
        with pytest.raises(TypeError):
            SimContext(codes=["sh600519"])

    def test_missing_codes_raises_type_error(self):
        with pytest.raises(TypeError):
            SimContext(strategy_name="balanced")

    def test_missing_all_required_raises_type_error(self):
        with pytest.raises(TypeError):
            SimContext()  # type: ignore[call-arg]


class TestSimContextAsDict:
    """TC-6: SimContext 可转为 dict（asdict）。"""

    def test_asdict(self):
        ctx = SimContext(
            strategy_name="balanced",
            codes=["sh600519", "sz000858"],
            top_n=3,
            holding_days=10,
            initial_capital=200000,
            commission=0.0003,
            stamp_tax=0.0005,
            slippage=0.002,
            weights={"quality": 0.5},
        )

        d = asdict(ctx)

        assert d["strategy_name"] == "balanced"
        assert d["codes"] == ["sh600519", "sz000858"]
        assert d["top_n"] == 3
        assert d["holding_days"] == 10
        assert d["initial_capital"] == 200000
        assert d["commission"] == 0.0003
        assert d["stamp_tax"] == 0.0005
        assert d["slippage"] == 0.002
        assert d["weights"] == {"quality": 0.5}

    def test_is_dataclass(self):
        assert is_dataclass(SimContext)


# ---------- 可变性 ----------


class TestAnalyzeContextMutable:
    """TC-7: AnalyzeContext 字段可变（非 frozen）。"""

    def test_fields_mutable(self):
        ctx = AnalyzeContext(
            code="sh600519",
            quote={},
            fin_records=[],
            strategy="balanced",
            filters={},
        )

        ctx.code = "sz000858"
        ctx.phase1 = True
        ctx.regime = "bear"
        ctx.no_chip = True
        ctx.kline_bars = [1, 2]

        assert ctx.code == "sz000858"
        assert ctx.phase1 is True
        assert ctx.regime == "bear"
        assert ctx.no_chip is True
        assert ctx.kline_bars == [1, 2]


class TestSimContextMutable:
    """TC-8: SimContext 字段可变（非 frozen）。"""

    def test_fields_mutable(self):
        ctx = SimContext(
            strategy_name="balanced",
            codes=["sh600519"],
        )

        ctx.strategy_name = "growth_momentum"
        ctx.codes = ["sz000858"]
        ctx.top_n = 10
        ctx.initial_capital = 500000
        ctx.commission = 0.0005
        ctx.weights = {"momentum": 0.6}

        assert ctx.strategy_name == "growth_momentum"
        assert ctx.codes == ["sz000858"]
        assert ctx.top_n == 10
        assert ctx.initial_capital == 500000
        assert ctx.commission == 0.0005
        assert ctx.weights == {"momentum": 0.6}
