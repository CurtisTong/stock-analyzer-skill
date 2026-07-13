"""测试 experts/veto_evaluator.py：一票否决条件评估器。

Phase 2 核心模块：填补 vote_engine.veto_results 的空接口。
验证两类条件分类：
- 刚性底线（RIGID）：触发则 risk_coeff=0.0，直接归零
- 弹性风险系数（ELASTIC）：0.2-1.0，折扣但非零
- 不可评估条件：标记 evaluable=False 跳过
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from experts.veto_evaluator import (
    evaluate_veto_conditions,
    ConditionResult,
    RIGID,
    ELASTIC,
    _check_goodwill_ratio,
    _check_fraud,
    _check_roe_low,
    _check_fcf_negative,
    _check_peg_high,
    _check_continuous_loss,
)
from experts.types import ExpertProfile


# ═══════════════════════════════════════════════════════════════
# 辅助构造
# ═══════════════════════════════════════════════════════════════


def _make_profile(
    name="buffett",
    veto_conditions=None,
    display_name="巴菲特",
    group="long_term",
):
    return ExpertProfile(
        name=name,
        display_name=display_name,
        group=group,
        style="价值投资",
        horizon="年",
        core_signal="ROE/PE/FCF",
        weights={"基本面": 42, "估值": 28, "技术面": 5, "情绪": 5, "安全边际": 20},
        veto_conditions=veto_conditions or [],
    )


# ═══════════════════════════════════════════════════════════════
# 刚性底线评估器
# ═══════════════════════════════════════════════════════════════


class TestCheckGoodwillRatio:
    """商誉/净资产 > 50% -> 刚性底线归零。"""

    def test_triggered_when_ratio_above_50(self):
        stock_data = {"finance": {"goodwill": 60, "net_assets": 100}}
        result = _check_goodwill_ratio(stock_data)
        assert result.triggered is True
        assert result.risk_coeff == 0.0
        assert "50%" in result.detail

    def test_not_triggered_when_ratio_below_50(self):
        stock_data = {"finance": {"goodwill": 30, "net_assets": 100}}
        result = _check_goodwill_ratio(stock_data)
        assert result.triggered is False
        assert result.risk_coeff == 1.0

    def test_not_evaluable_when_data_missing(self):
        stock_data = {"finance": {}}
        result = _check_goodwill_ratio(stock_data)
        assert result.evaluable is False


class TestCheckFraud:
    """管理层欺诈/财务造假 -> 刚性底线归零。"""

    def test_triggered_when_fraud_flag_true(self):
        stock_data = {"fraud_flag": True}
        result = _check_fraud(stock_data)
        assert result.triggered is True
        assert result.risk_coeff == 0.0

    def test_not_triggered_when_fraud_flag_false(self):
        stock_data = {"fraud_flag": False}
        result = _check_fraud(stock_data)
        assert result.triggered is False

    def test_not_evaluable_when_no_flag(self):
        stock_data = {}
        result = _check_fraud(stock_data)
        assert result.evaluable is False


# ═══════════════════════════════════════════════════════════════
# 弹性风险系数评估器
# ═══════════════════════════════════════════════════════════════


class TestCheckRoeLow:
    """ROE < 10% 或负债率 > 70% -> 弹性风险系数。"""

    def test_triggered_roe_below_10(self):
        stock_data = {"finance": {"ROEJQ": 8.0, "ZCFZL": 45.0}}
        result = _check_roe_low(stock_data)
        assert result.triggered is True
        assert 0 < result.risk_coeff < 1.0  # 弹性，非零

    def test_severe_roe_below_5(self):
        stock_data = {"finance": {"ROEJQ": 3.0, "ZCFZL": 45.0}}
        result = _check_roe_low(stock_data)
        assert result.triggered is True
        assert result.risk_coeff == 0.3  # 严重风险

    def test_triggered_debt_above_70(self):
        stock_data = {"finance": {"ROEJQ": 15.0, "ZCFZL": 75.0}}
        result = _check_roe_low(stock_data)
        assert result.triggered is True
        assert result.risk_coeff == 0.5  # 中等风险

    def test_not_triggered(self):
        stock_data = {"finance": {"ROEJQ": 20.0, "ZCFZL": 40.0}}
        result = _check_roe_low(stock_data)
        assert result.triggered is False

    def test_not_evaluable_when_data_missing(self):
        stock_data = {"finance": {}}
        result = _check_roe_low(stock_data)
        assert result.evaluable is False


class TestCheckFcfNegative:
    """FCF 为负 -> 弹性风险系数。"""

    def test_triggered_when_fcf_negative(self):
        stock_data = {"finance": {"MGJYXJJE": -1.5}}
        result = _check_fcf_negative(stock_data)
        assert result.triggered is True
        assert result.risk_coeff == 0.6

    def test_not_triggered_when_fcf_positive(self):
        stock_data = {"finance": {"MGJYXJJE": 2.0}}
        result = _check_fcf_negative(stock_data)
        assert result.triggered is False

    def test_not_evaluable_when_data_missing(self):
        stock_data = {"finance": {}}
        result = _check_fcf_negative(stock_data)
        assert result.evaluable is False


class TestCheckPegHigh:
    """PEG > 2.5 -> 弹性风险系数。"""

    def test_triggered_when_peg_above_25(self):
        stock_data = {
            "quote": {"pe": 50},
            "finance": {"PARENTNETPROFITTZ": 10},
        }
        result = _check_peg_high(stock_data)
        assert result.triggered is True
        assert result.risk_coeff == 0.4

    def test_not_triggered_when_peg_below_25(self):
        stock_data = {
            "quote": {"pe": 20},
            "finance": {"PARENTNETPROFITTZ": 15},
        }
        result = _check_peg_high(stock_data)
        assert result.triggered is False

    def test_not_evaluable_when_growth_zero(self):
        stock_data = {"quote": {"pe": 20}, "finance": {"PARENTNETPROFITTZ": 0}}
        result = _check_peg_high(stock_data)
        assert result.evaluable is False


class TestCheckContinuousLoss:
    """连续2年亏损 -> 弹性风险系数。"""

    def test_triggered_when_all_negative(self):
        stock_data = {
            "finance_records": [
                {"EPSJB": -0.5}, {"EPSJB": -0.3}, {"EPSJB": -0.4}, {"EPSJB": -0.2}
            ]
        }
        result = _check_continuous_loss(stock_data)
        assert result.triggered is True
        assert result.risk_coeff == 0.3

    def test_not_triggered_when_profitable(self):
        stock_data = {
            "finance_records": [
                {"EPSJB": 0.5}, {"EPSJB": 0.3}, {"EPSJB": 0.4}, {"EPSJB": 0.2}
            ]
        }
        result = _check_continuous_loss(stock_data)
        assert result.triggered is False

    def test_not_evaluable_when_insufficient_periods(self):
        stock_data = {"finance_records": [{"EPSJB": -0.5}]}
        result = _check_continuous_loss(stock_data)
        assert result.evaluable is False


# ═══════════════════════════════════════════════════════════════
# evaluate_veto_conditions 主入口
# ═══════════════════════════════════════════════════════════════


class TestEvaluateVetoConditions:
    """主入口：评估所有专家的 veto_conditions。"""

    def test_returns_empty_for_no_veto_conditions(self):
        profiles = {"buffett": _make_profile(veto_conditions=[])}
        veto, coeff = evaluate_veto_conditions({}, profiles)
        assert veto == {}
        assert coeff == {}

    def test_rigid_triggers_zero_coeff(self):
        """刚性底线触发 -> risk_coeff=0.0。"""
        profiles = {
            "buffett": _make_profile(
                veto_conditions=["公司涉财务造假或管理层失信"]
            )
        }
        stock_data = {"fraud_flag": True}
        veto, coeff = evaluate_veto_conditions(stock_data, profiles)
        assert coeff["buffett"] == 0.0
        assert veto["buffett"]["公司涉财务造假或管理层失信"]["triggered"] is True
        assert veto["buffett"]["公司涉财务造假或管理层失信"]["risk_coeff"] == 0.0

    def test_elastic_triggers_discount_coeff(self):
        """弹性风险系数触发 -> 0 < coeff < 1.0。"""
        profiles = {
            "buffett": _make_profile(
                veto_conditions=["ROE < 10% 或负债率 > 70%（金融业除外）"]
            )
        }
        stock_data = {"finance": {"ROEJQ": 8.0, "ZCFZL": 45.0}}
        veto, coeff = evaluate_veto_conditions(stock_data, profiles)
        assert 0 < coeff["buffett"] < 1.0

    def test_no_trigger_returns_coeff_1(self):
        """无触发条件 -> coeff=1.0（无折扣）。"""
        profiles = {
            "buffett": _make_profile(
                veto_conditions=["ROE < 10% 或负债率 > 70%（金融业除外）"]
            )
        }
        stock_data = {"finance": {"ROEJQ": 20.0, "ZCFZL": 40.0}}
        veto, coeff = evaluate_veto_conditions(stock_data, profiles)
        assert coeff["buffett"] == 1.0

    def test_unevaluable_condition_marked(self):
        """不可评估条件标记 evaluable=False。"""
        profiles = {
            "risk_manager": _make_profile(
                name="risk_manager",
                veto_conditions=["市场周期顶部（所有人同边 + 流动性枯竭）"],
            )
        }
        veto, coeff = evaluate_veto_conditions({}, profiles)
        cond = veto["risk_manager"]["市场周期顶部（所有人同边 + 流动性枯竭）"]
        assert cond["evaluable"] is False
        assert coeff["risk_manager"] == 1.0  # 不影响系数

    def test_composite_coeff_takes_minimum(self):
        """复合系数取所有触发条件中最低的 risk_coeff（最严厉折扣）。"""
        profiles = {
            "buffett": _make_profile(
                veto_conditions=[
                    "ROE < 10% 或负债率 > 70%（金融业除外）",  # coeff=0.5
                    "公司涉财务造假或管理层失信",  # coeff=0.0
                ]
            )
        }
        stock_data = {
            "finance": {"ROEJQ": 8.0, "ZCFZL": 45.0},
            "fraud_flag": True,
        }
        veto, coeff = evaluate_veto_conditions(stock_data, profiles)
        assert coeff["buffett"] == 0.0  # 取最低（最严厉）

    def test_multiple_experts(self):
        """多专家独立评估。"""
        profiles = {
            "buffett": _make_profile(
                veto_conditions=["ROE < 10% 或负债率 > 70%（金融业除外）"]
            ),
            "lynch": _make_profile(
                name="lynch",
                display_name="彼得·林奇",
                group="long_term",
                veto_conditions=["PEG > 2.5（增速无法消化估值）"],
            ),
        }
        stock_data = {
            "finance": {"ROEJQ": 8.0, "ZCFZL": 45.0, "PARENTNETPROFITTZ": 10},
            "quote": {"pe": 50},
        }
        veto, coeff = evaluate_veto_conditions(stock_data, profiles)
        assert coeff["buffett"] < 1.0  # ROE 低触发
        assert coeff["lynch"] < 1.0  # PEG 高触发

    def test_evaluator_exception_handled(self):
        """评估器异常不崩溃，标记不可评估。"""
        profiles = {
            "buffett": _make_profile(
                veto_conditions=["ROE < 10% 或负债率 > 70%（金融业除外）"]
            )
        }
        # 传入会导致异常的数据（None 作为 finance）
        stock_data = {"finance": None}
        veto, coeff = evaluate_veto_conditions(stock_data, profiles)
        # 不崩溃即可，coeff 应为 1.0（无触发或不可评估）
        assert "buffett" in coeff


# ═══════════════════════════════════════════════════════════════
# ConditionResult
# ═══════════════════════════════════════════════════════════════


class TestConditionResult:
    def test_default_values(self):
        r = ConditionResult()
        assert r.triggered is False
        assert r.risk_coeff == 1.0
        assert r.evaluable is True
        assert r.detail == ""

    def test_to_dict(self):
        r = ConditionResult(triggered=True, risk_coeff=0.5, detail="test")
        d = r.to_dict()
        assert d["triggered"] is True
        assert d["risk_coeff"] == 0.5
        assert d["detail"] == "test"
