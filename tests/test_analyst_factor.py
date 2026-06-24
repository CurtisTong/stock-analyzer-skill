"""分析师预期因子测试。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from strategies.factors.analyst import analyst_expectation_score


class TestAnalystExpectationScore:
    """analyst_expectation_score 函数测试。"""

    def test_neutral_score_no_data(self):
        """无数据时返回中性分 50。"""
        result = analyst_expectation_score({}, {})
        assert result == 50.0

    def test_target_price_upside_large(self):
        """目标价大幅上行空间（>30%）加 25 分。"""
        quote = {"price": 100}
        fin = {"target_price": 140}  # 40% upside
        result = analyst_expectation_score(quote, fin)
        assert result == 75.0  # 50 + 25

    def test_target_price_upside_medium(self):
        """目标价中等上行空间（15-30%）加 18 分。"""
        quote = {"price": 100}
        fin = {"target_price": 120}  # 20% upside
        result = analyst_expectation_score(quote, fin)
        assert result == 68.0  # 50 + 18

    def test_target_price_upside_small(self):
        """目标价小幅上行空间（5-15%）加 10 分。"""
        quote = {"price": 100}
        fin = {"target_price": 110}  # 10% upside
        result = analyst_expectation_score(quote, fin)
        assert result == 60.0  # 50 + 10

    def test_target_price_downside_large(self):
        """目标价大幅下行（<-20%）扣 15 分。"""
        quote = {"price": 100}
        fin = {"target_price": 75}  # -25% downside
        result = analyst_expectation_score(quote, fin)
        assert result == 35.0  # 50 - 15

    def test_target_price_downside_medium(self):
        """目标价中等下行（-10%~-20%）扣 8 分。"""
        quote = {"price": 100}
        fin = {"target_price": 85}  # -15% downside
        result = analyst_expectation_score(quote, fin)
        assert result == 42.0  # 50 - 8

    def test_high_growth_with_revenue(self):
        """高增长 + 营收配合加 15 分。"""
        quote = {"price": 100}
        fin = {"net_profit_yoy": 60, "revenue_yoy": 25}
        result = analyst_expectation_score(quote, fin)
        assert result == 65.0  # 50 + 15

    def test_profit_growth_medium(self):
        """中等利润增长（30-50%）加 10 分。"""
        quote = {"price": 100}
        fin = {"net_profit_yoy": 40}
        result = analyst_expectation_score(quote, fin)
        assert result == 60.0  # 50 + 10

    def test_profit_growth_small(self):
        """小幅利润增长（10-30%）加 5 分。"""
        quote = {"price": 100}
        fin = {"net_profit_yoy": 15}
        result = analyst_expectation_score(quote, fin)
        assert result == 55.0  # 50 + 5

    def test_profit_decline_large(self):
        """利润大幅下滑（<-30%）扣 15 分。"""
        quote = {"price": 100}
        fin = {"net_profit_yoy": -40}
        result = analyst_expectation_score(quote, fin)
        assert result == 35.0  # 50 - 15

    def test_profit_decline_medium(self):
        """利润中等下滑（-10%~-30%）扣 8 分。"""
        quote = {"price": 100}
        fin = {"net_profit_yoy": -20}
        result = analyst_expectation_score(quote, fin)
        assert result == 42.0  # 50 - 8

    def test_institution_coverage_high(self):
        """大量机构覆盖（>20）加 10 分。"""
        quote = {"price": 100}
        fin = {"institution_count": 30}
        result = analyst_expectation_score(quote, fin)
        assert result == 60.0  # 50 + 10

    def test_institution_coverage_medium(self):
        """中等机构覆盖（5-20）加 5 分。"""
        quote = {"price": 100}
        fin = {"institution_count": 10}
        result = analyst_expectation_score(quote, fin)
        assert result == 55.0  # 50 + 5

    def test_institution_coverage_none(self):
        """无机构覆盖不扣分。"""
        quote = {"price": 100}
        fin = {"institution_count": 0}
        result = analyst_expectation_score(quote, fin)
        assert result == 50.0

    def test_combined_signals(self):
        """多个信号叠加。"""
        quote = {"price": 100}
        fin = {
            "target_price": 130,  # 30% upside → +18
            "net_profit_yoy": 40,  # medium growth → +10
            "institution_count": 15,  # medium coverage → +5
        }
        result = analyst_expectation_score(quote, fin)
        assert result == 83.0  # 50 + 18 + 10 + 5

    def test_negative_signals(self):
        """多个负面信号叠加。"""
        quote = {"price": 100}
        fin = {
            "target_price": 70,  # -30% downside → -15
            "net_profit_yoy": -50,  # large decline → -15
        }
        result = analyst_expectation_score(quote, fin)
        assert result == 20.0  # 50 - 15 - 15

    def test_score_clamped_high(self):
        """分数不超过 100。"""
        quote = {"price": 10}
        fin = {
            "target_price": 50,  # 400% upside → +25
            "net_profit_yoy": 100,  # high growth → +15
            "revenue_yoy": 50,
            "institution_count": 50,  # high coverage → +10
        }
        result = analyst_expectation_score(quote, fin)
        assert result == 100.0  # clamped at 100

    def test_score_clamped_low(self):
        """分数不低于 0。"""
        quote = {"price": 100}
        fin = {
            "target_price": 10,  # -90% downside → -15
            "net_profit_yoy": -80,  # large decline → -15
        }
        result = analyst_expectation_score(quote, fin)
        assert result == 20.0  # 50 - 15 - 15 = 20 (not below 0)

    def test_alternative_field_names(self):
        """支持东财原始字段名。"""
        quote = {"price": 100}
        fin = {
            "ANALYST_TARGET_PRICE": 120,  # 20% upside → +18
            "PARENTNETPROFITTZ": 40,  # medium growth → +10
            "TOTALOPERATEREVETZ": 25,
            "HOLD_ORG_NUM": 15,  # medium coverage → +5
        }
        result = analyst_expectation_score(quote, fin)
        assert result == 83.0  # 50 + 18 + 10 + 5
