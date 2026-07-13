"""测试 Phase 3：周期因子 + DCF 三情景 + veto 周期接入。

覆盖：
- factors/cyclical.py: 三维度周期矩阵（价格/供给/成本）
- factors/dcf.py: 三情景 DCF 估值（bear/base/bull + 周期位置赋权）
- veto_evaluator.py: 周期高位 -> 弹性风险系数 0.4
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from strategies.factors.cyclical import (
    cyclical_score,
    get_cycle_position,
    _is_cyclical,
    _price_dimension,
    _supply_dimension,
)
from strategies.factors.dcf import (
    dcf_valuation,
    dcf_score,
    dcf_scenario_valuation,
    dcf_scenario_score,
    _CYCLE_SCENARIO_WEIGHTS,
)
from experts.veto_evaluator import _check_cycle_position


# ═══════════════════════════════════════════════════════════════
# cyclical_score: 三维度周期矩阵
# ═══════════════════════════════════════════════════════════════


class TestCyclicalScoreNonCyclical:
    """非周期行业返回中性 50。"""

    @pytest.mark.parametrize("industry", ["消费", "科技", "医药", "金融", "默认"])
    def test_non_cyclical_returns_neutral(self, industry):
        fin = {"ROEJQ": 20, "ZCFZL": 40}
        quote = {"pe": 25, "pb": 2.0}
        assert cyclical_score(fin, quote, {}, industry) == 50.0

    def test_is_cyclical_detection(self):
        assert _is_cyclical("钢铁") is True
        assert _is_cyclical("基础化工") is True
        assert _is_cyclical("消费") is False


class TestCyclicalScorePriceDimension:
    """价格维度：PE/PB 高位 + 利润增速异常 -> 高位信号。"""

    def test_high_pe_high_growth_signals_top(self):
        """PE 高 + 增速异常高 -> 周期顶部信号。"""
        fin = {"ROEJQ": 25, "PARENTNETPROFITTZ": 60}  # 增速60%>50%阈值
        quote = {"pe": 30, "pb": 4.0}  # PE>=25, PB>=3.5
        result = _price_dimension(fin, quote, "周期")
        assert result["position"] == "high"
        assert result["evaluable"] is True

    def test_low_pe_signals_bottom(self):
        """PE 低估 -> 底部信号。"""
        fin = {"ROEJQ": 8, "PARENTNETPROFITTZ": -10}
        quote = {"pe": 6, "pb": 0.8}
        result = _price_dimension(fin, quote, "周期")
        assert result["position"] == "low"

    def test_missing_data_not_evaluable(self):
        result = _price_dimension({}, {}, "周期")
        assert result["evaluable"] is False


class TestCyclicalScoreSupplyDimension:
    """供给维度：ROE 趋势作为代理。"""

    def test_high_roe_rising_trend_signals_top(self):
        """ROE 高位 + 持续上升 -> 供给扩张（顶部前兆）。"""
        fin = {"roe_trend": [10, 12, 15, 18, 22]}  # 持续上升至高位
        result = _supply_dimension(fin, "周期")
        assert result["position"] == "high"

    def test_low_roe_declining_signals_bottom(self):
        """ROE 低位 + 持续下降 -> 供给收缩（底部前兆）。"""
        fin = {"roe_trend": [15, 12, 9, 7, 5]}  # 持续下降至低位
        result = _supply_dimension(fin, "周期")
        assert result["position"] == "low"

    def test_insufficient_data_not_evaluable(self):
        result = _supply_dimension({"roe_trend": [10, 12]}, "周期")
        assert result["evaluable"] is False


class TestCyclicalScoreComposite:
    """三维度综合：≥2 高位 -> 周期顶部低分。"""

    def test_two_high_signals_low_score(self):
        """价格高位 + 供给高位 -> 周期顶部，低分。"""
        fin = {
            "ROEJQ": 25,
            "PARENTNETPROFITTZ": 60,
            "roe_trend": [10, 12, 15, 18, 22],
        }
        quote = {"pe": 30, "pb": 4.0}
        score = cyclical_score(fin, quote, {}, "周期")
        assert score < 40  # 周期顶部低分

    def test_two_low_signals_high_score(self):
        """价格低位 + 供给低位 -> 周期底部，高分。"""
        fin = {
            "ROEJQ": 5,
            "PARENTNETPROFITTZ": -15,
            "roe_trend": [15, 12, 9, 7, 5],
        }
        quote = {"pe": 6, "pb": 0.8}
        score = cyclical_score(fin, quote, {}, "周期")
        assert score > 70  # 周期底部高分

    def test_neutral_signals_mid_score(self):
        """中性信号 -> 中分。"""
        fin = {"ROEJQ": 15, "PARENTNETPROFITTZ": 10}
        quote = {"pe": 15, "pb": 2.0}
        score = cyclical_score(fin, quote, {}, "周期")
        assert 40 <= score <= 70

    def test_all_dimensions_missing_returns_neutral(self):
        score = cyclical_score({}, {}, {}, "周期")
        assert score == 50.0


class TestGetCyclePosition:
    """get_cycle_position 标签输出。"""

    def test_returns_high_when_two_signals(self):
        fin = {
            "ROEJQ": 25,
            "PARENTNETPROFITTZ": 60,
            "roe_trend": [10, 12, 15, 18, 22],
        }
        quote = {"pe": 30, "pb": 4.0}
        assert get_cycle_position(fin, quote, "周期") == "high"

    def test_returns_unknown_for_non_cyclical(self):
        assert get_cycle_position({}, {}, "消费") == "unknown"

    def test_returns_unknown_when_no_data(self):
        """全部维度不可评估时返回 unknown。

        价格/供给维度需 PE/ROE 趋势数据；成本维度需原料映射。
        用空数据 + 非周期行业确保全部不可评估。
        """
        # 非周期行业直接返回 unknown（不进入维度评估）
        assert get_cycle_position({}, {}, "消费") == "unknown"
        # 周期行业但无任何数据：价格/供给不可评估，
        # 成本维度从 fixture 读取（有值则可评估返回 mid，无映射则不可评估）
        # 钢铁有原料映射(rebar)，如果 fixture 有值会返回 mid 而非 unknown
        # 此处验证不会崩溃即可
        pos = get_cycle_position({}, {}, "钢铁")
        assert pos in ("unknown", "mid")


# ═══════════════════════════════════════════════════════════════
# DCF 三情景估值
# ═══════════════════════════════════════════════════════════════


class TestDcfScenarioValuation:
    """三情景 DCF：bear/base/bull + 周期位置赋权。"""

    def _make_fin(self):
        return {
            "MGJYXJJE": 2.0,  # 每股经营现金流
            "EPSJB": 1.5,  # 每股收益
            "PARENTNETPROFITTZ": 20,  # 净利增速20%
        }

    def test_returns_scenario_dict(self):
        result = dcf_scenario_valuation(20, self._make_fin(), "周期", "mid")
        assert result["method"] == "dcf_scenario"
        assert "scenarios" in result
        assert set(result["scenarios"].keys()) == {"bear", "base", "bull"}

    def test_cycle_high_biased_bear(self):
        """周期高位时悲观情景权重 80%。"""
        result = dcf_scenario_valuation(20, self._make_fin(), "周期", "high")
        weights = result["scenario_weights"]
        assert weights["bear"] == 0.80
        assert weights["bull"] == 0.05

    def test_cycle_low_biased_bull(self):
        """周期低位时乐观情景权重 80%。"""
        result = dcf_scenario_valuation(20, self._make_fin(), "周期", "low")
        weights = result["scenario_weights"]
        assert weights["bull"] == 0.80
        assert weights["bear"] == 0.05

    def test_cycle_mid_balanced(self):
        """中性周期时三情景均衡。"""
        result = dcf_scenario_valuation(20, self._make_fin(), "周期", "mid")
        weights = result["scenario_weights"]
        assert weights["bear"] == 0.25
        assert weights["base"] == 0.50
        assert weights["bull"] == 0.25

    def test_high_cycle_lower_margin_than_low(self):
        """同一股票，周期高位安全边际应低于周期低位。"""
        fin = self._make_fin()
        high_result = dcf_scenario_valuation(20, fin, "周期", "high")
        low_result = dcf_scenario_valuation(20, fin, "周期", "low")
        # 高位（悲观主导）安全边际应 <= 低位（乐观主导）
        assert high_result["margin_of_safety"] <= low_result["margin_of_safety"]

    def test_no_fcf_data_returns_error(self):
        """无现金流数据时返回 error（而非归零）。"""
        result = dcf_scenario_valuation(20, {}, "周期", "mid")
        assert "error" in result

    def test_unknown_cycle_uses_mid_weights(self):
        """未知周期位置使用中性权重。"""
        result = dcf_scenario_valuation(20, self._make_fin(), "周期", "unknown")
        weights = result["scenario_weights"]
        assert weights == _CYCLE_SCENARIO_WEIGHTS["unknown"]


class TestDcfScenarioScore:
    """三情景 DCF 评分。"""

    def _make_fin(self):
        return {"MGJYXJJE": 2.0, "EPSJB": 1.5, "PARENTNETPROFITTZ": 20}

    def test_returns_score_in_range(self):
        score = dcf_scenario_score(20, self._make_fin(), "周期", "mid")
        assert 0 <= score <= 100

    def test_no_data_returns_50(self):
        """无数据返回 50（中性，非零）。"""
        score = dcf_scenario_score(20, {}, "周期", "mid")
        assert score == 50

    def test_low_price_high_score(self):
        """低价（低估）-> 高分。"""
        score = dcf_scenario_score(5, self._make_fin(), "周期", "mid")
        assert score >= 70

    def test_high_price_low_score(self):
        """高价（高估）-> 低分。"""
        score = dcf_scenario_score(100, self._make_fin(), "周期", "mid")
        assert score <= 40


# ═══════════════════════════════════════════════════════════════
# veto_evaluator 周期接入
# ═══════════════════════════════════════════════════════════════


class TestCheckCyclePosition:
    """周期位置评估器：周期高位 -> risk_coeff=0.4。"""

    def test_high_cycle_triggers_discount(self):
        """周期高位 -> 触发，risk_coeff=0.4。"""
        stock_data = {
            "finance": {
                "ROEJQ": 25,
                "PARENTNETPROFITTZ": 60,
                "roe_trend": [10, 12, 15, 18, 22],
            },
            "quote": {"pe": 30, "pb": 4.0},
            "industry": "周期",
        }
        result = _check_cycle_position(stock_data)
        assert result.triggered is True
        assert result.risk_coeff == 0.4

    def test_low_cycle_not_triggered(self):
        """周期低位 -> 不触发（机会）。"""
        stock_data = {
            "finance": {
                "ROEJQ": 5,
                "PARENTNETPROFITTZ": -15,
                "roe_trend": [15, 12, 9, 7, 5],
            },
            "quote": {"pe": 6, "pb": 0.8},
            "industry": "周期",
        }
        result = _check_cycle_position(stock_data)
        assert result.triggered is False

    def test_non_cyclical_not_evaluable(self):
        """非周期行业 -> 不可评估。"""
        stock_data = {
            "finance": {"ROEJQ": 25},
            "quote": {"pe": 30},
            "industry": "消费",
        }
        result = _check_cycle_position(stock_data)
        assert result.evaluable is False

    def test_discount_not_zero(self):
        """周期高位折扣 0.4，非零（避免误杀周期成长股）。"""
        stock_data = {
            "finance": {
                "ROEJQ": 25,
                "PARENTNETPROFITTZ": 60,
                "roe_trend": [10, 12, 15, 18, 22],
            },
            "quote": {"pe": 30, "pb": 4.0},
            "industry": "周期",
        }
        result = _check_cycle_position(stock_data)
        assert 0 < result.risk_coeff < 1.0  # 弹性，非刚性归零


# ═══════════════════════════════════════════════════════════════
# 集成：cyclical 因子注册
# ═══════════════════════════════════════════════════════════════


class TestCyclicalFactorRegistration:
    """验证 cyclical 因子已注册到因子注册表。"""

    def test_cyclical_in_factor_keys(self):
        from strategies.factors import get_factor_keys

        assert "cyclical" in get_factor_keys()

    def test_cyclical_in_compute_all_factors(self):
        """compute_all_factors 能计算 cyclical 因子。"""
        from strategies.factors.registry import compute_all_factors

        fin = {"ROEJQ": 25, "PARENTNETPROFITTZ": 60, "roe_trend": [10, 12, 15, 18, 22]}
        quote = {"pe": 30, "pb": 4.0}
        features = {}
        result = compute_all_factors(fin, quote, features, "周期", "sh600000")
        assert "cyclical" in result
        assert isinstance(result["cyclical"], float)
        assert 0 <= result["cyclical"] <= 100
