"""DCF 估值模型测试。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from strategies.factors.dcf import dcf_valuation, dcf_score


class TestDcfValuation:
    """dcf_valuation 函数测试。"""

    def test_basic_valuation(self):
        """基本 DCF 估值计算。"""
        fin = {"eps": 5.0, "ocf_per_share": 8.0}
        result = dcf_valuation(100, fin, growth_rate=0.15)
        assert result["method"] == "dcf"
        assert result["intrinsic_value"] > 0
        assert result["fcf_per_share"] == 5.6  # 8.0 * 0.7
        assert result["growth_rate"] == 15.0

    def test_valuation_with_eps_only(self):
        """仅有 EPS 数据时回退到净利润估算。"""
        fin = {"eps": 3.0}
        result = dcf_valuation(50, fin, growth_rate=0.10)
        assert result["fcf_per_share"] == 2.1  # 3.0 * 0.7
        assert result["intrinsic_value"] > 0

    def test_no_data_returns_error(self):
        """无现金流数据时返回错误。"""
        fin = {}
        result = dcf_valuation(100, fin)
        assert result["intrinsic_value"] == 0
        assert result.get("error") == "无可用现金流数据"

    def test_margin_of_safety_undervalued(self):
        """低估时安全边际为正。"""
        fin = {"eps": 10.0, "ocf_per_share": 15.0}
        result = dcf_valuation(50, fin, growth_rate=0.20)
        assert result["margin_of_safety"] > 0

    def test_margin_of_safety_overvalued(self):
        """高估时安全边际为负。"""
        fin = {"eps": 1.0, "ocf_per_share": 1.5}
        result = dcf_valuation(500, fin, growth_rate=0.05)
        assert result["margin_of_safety"] < 0

    def test_growth_rate_auto_infer(self):
        """自动推断增长率（优先用 3 年复合增速）。"""
        fin = {"eps": 5.0, "net_profit_cagr_3y": 20.0}
        result = dcf_valuation(100, fin)
        assert result["growth_rate"] == 20.0

    def test_growth_rate_fallback_to_yoy(self):
        """回退到单期增速。"""
        fin = {"eps": 5.0, "net_profit_yoy": 25.0}
        result = dcf_valuation(100, fin)
        assert result["growth_rate"] == 25.0

    def test_growth_rate_default(self):
        """无增速数据时默认 5%。"""
        fin = {"eps": 5.0}
        result = dcf_valuation(100, fin)
        assert result["growth_rate"] == 5.0

    def test_growth_rate_capped_at_30(self):
        """增长率上限 30%。"""
        fin = {"eps": 5.0, "net_profit_cagr_3y": 50.0}
        result = dcf_valuation(100, fin)
        assert result["growth_rate"] == 30.0

    def test_growth_rate_floor_at_1(self):
        """增长率下限 1%。"""
        fin = {"eps": 5.0}
        result = dcf_valuation(100, fin, growth_rate=-0.05)
        assert result["growth_rate"] == 1.0

    def test_custom_parameters(self):
        """自定义折现率和永续增长率。"""
        fin = {"eps": 5.0}
        result = dcf_valuation(
            100, fin, growth_rate=0.10, discount_rate=0.12, terminal_growth=0.02
        )
        assert result["discount_rate"] == 12.0
        assert result["terminal_growth"] == 2.0

    def test_alternative_field_names(self):
        """支持东财原始字段名。"""
        fin = {"EPSJB": 5.0, "MGJYXJJE": 8.0}
        result = dcf_valuation(100, fin, growth_rate=0.15)
        assert result["fcf_per_share"] == 5.6


class TestDcfScore:
    """dcf_score 函数测试。"""

    def test_undervalued_high(self):
        """极度低估得 90 分。"""
        fin = {"eps": 10.0, "ocf_per_share": 15.0}
        # 高增长 + 低价格 → 高安全边际
        score = dcf_score(30, fin, "默认")
        assert score >= 70

    def test_overvalued(self):
        """明显高估得 20 分。"""
        fin = {"eps": 0.5, "ocf_per_share": 0.7}
        score = dcf_score(500, fin, "默认")
        assert score == 20

    def test_no_data_neutral(self):
        """无数据返回中性分 50。"""
        score = dcf_score(100, {}, "默认")
        assert score == 50

    def test_reasonable_valuation(self):
        """合理估值范围。"""
        fin = {"eps": 5.0, "ocf_per_share": 7.0}
        score = dcf_score(100, fin, "默认")
        assert 20 <= score <= 90
