"""动态 PE + 目标 PE 论证测试。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from strategies.factors.valuation_ext import dynamic_pe, target_pe_justification


class TestDynamicPe:
    """dynamic_pe 多口径动态 PE 测试（审查 #11）。"""

    def test_three_scenarios(self):
        """宝丰数据：三口径 PE 均正确计算。"""
        result = dynamic_pe(
            1519,
            {
                "q1_annualized": 146.44,
                "h1_forecast_mid": 97.5,
                "fy_forecast": 145.1,
            },
        )
        # Q1 年化: 1519 / 146.44 ≈ 10.37
        assert abs(result["pe_q1_annualized"] - 10.37) < 0.1
        # H1 预增: 1519 / (97.5 × 2) ≈ 7.79
        assert abs(result["pe_h1_forecast"] - 7.79) < 0.1
        # FY 预测: 1519 / 145.1 ≈ 10.47
        assert abs(result["pe_fy_consensus"] - 10.47) < 0.1
        # 推荐口径优先 fy_consensus
        assert result["recommended_pe"] == result["pe_fy_consensus"]
        assert "机构全年预测" in result["recommended_basis"]

    def test_fallback_to_h1_when_no_fy(self):
        """无机构全年预测时，回退到 H1 预增口径。"""
        result = dynamic_pe(
            1519,
            {
                "q1_annualized": 146.44,
                "h1_forecast_mid": 97.5,
            },
        )
        assert result["recommended_pe"] == result["pe_h1_forecast"]
        assert "H1 预增修正" in result["recommended_basis"]

    def test_fallback_to_q1_only(self):
        """仅有 Q1 数据时，回退到 Q1 年化口径。"""
        result = dynamic_pe(1519, {"q1_annualized": 146.44})
        assert result["recommended_pe"] == result["pe_q1_annualized"]
        assert "Q1 年化" in result["recommended_basis"]
        assert len(result["available_scenarios"]) == 1

    def test_zero_market_cap(self):
        """市值为 0 时不崩溃，返回全 0。"""
        result = dynamic_pe(0, {"q1_annualized": 100})
        assert result["recommended_pe"] == 0.0
        assert result["available_scenarios"] == []

    def test_empty_scenarios(self):
        """无净利情景时返回推荐 0。"""
        result = dynamic_pe(1519, {})
        assert result["recommended_pe"] == 0.0
        assert "无可用" in result["recommended_basis"]

    def test_zero_profit_scenario_skipped(self):
        """净利为 0 的口径跳过计算。"""
        result = dynamic_pe(
            1519,
            {
                "q1_annualized": 0,  # 跳过
                "h1_forecast_mid": 97.5,  # 使用
            },
        )
        assert result["pe_q1_annualized"] == 0.0
        assert result["pe_h1_forecast"] > 0
        assert "h1_forecast" in result["available_scenarios"]
        assert "q1_annualized" not in result["available_scenarios"]


class TestTargetPeJustification:
    """target_pe_justification 目标 PE 论证测试（审查 #24）。"""

    def test_two_factor_weighted(self):
        """可比公司 + 机构隐含 PE 等权加权。"""
        result = target_pe_justification(
            comparable_pe=17.0,
            peg=0.4,
            consensus_implied_pe=12.5,
        )
        # (17.0 + 12.5) / 2 = 14.75
        assert abs(result["target_pe"] - 14.75) < 0.1
        assert "可比公司" in result["basis"]
        assert "机构目标价隐含" in result["basis"]
        assert "PEG=0.40" in result["basis"]

    def test_peg_low_undervalued_note(self):
        """PEG < 0.8 标注显著低估。"""
        result = target_pe_justification(
            comparable_pe=15.0, peg=0.5, consensus_implied_pe=12.0
        )
        assert "显著低估" in result["basis"]

    def test_peg_high_overvalued_note(self):
        """PEG > 1.5 标注偏高。"""
        result = target_pe_justification(
            comparable_pe=15.0, peg=2.0, consensus_implied_pe=12.0
        )
        assert "偏高" in result["basis"]

    def test_only_comparable_pe(self):
        """仅有可比公司 PE 时单因素。"""
        result = target_pe_justification(
            comparable_pe=17.0, peg=0, consensus_implied_pe=0
        )
        assert result["target_pe"] == 17.0
        assert len(result["weighting"]) > 0

    def test_no_factors(self):
        """无任何依据时目标 PE 为 0。"""
        result = target_pe_justification(comparable_pe=0, peg=0, consensus_implied_pe=0)
        assert result["target_pe"] == 0.0
        assert "缺乏支撑" in result["basis"]
