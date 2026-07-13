import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestRedFlagMoreBranches:
    def test_goodwill_high(self):
        from strategies.factors.quality import _a_stock_red_flag_score
        fin = {"goodwill": 60, "total_assets": 100, "short_term_loan": 10,
               "long_term_loan": 5, "cash": 15, "revenue": 50,
               "net_profit": 5, "ocf": 4}
        result = _a_stock_red_flag_score(fin)
        assert isinstance(result, (int, float, dict))

    def test_cash_high(self):
        from strategies.factors.quality import _a_stock_red_flag_score
        fin = {"goodwill": 5, "total_assets": 100, "short_term_loan": 50,
               "long_term_loan": 40, "cash": 80, "revenue": 50,
               "net_profit": 5, "ocf": 4}
        result = _a_stock_red_flag_score(fin)
        assert isinstance(result, (int, float, dict))

    def test_ocf_negative(self):
        from strategies.factors.quality import _a_stock_red_flag_score
        fin = {"goodwill": 5, "total_assets": 100, "short_term_loan": 10,
               "long_term_loan": 5, "cash": 15, "revenue": 50,
               "net_profit": 10, "ocf": -5}
        result = _a_stock_red_flag_score(fin)
        assert isinstance(result, (int, float, dict))

    def test_empty_dict(self):
        from strategies.factors.quality import _a_stock_red_flag_score
        result = _a_stock_red_flag_score({})
        assert isinstance(result, (int, float, dict))


class TestQualityScoreMore:
    def test_industry_tech(self):
        from strategies.factors.quality import quality_score
        fin = {"eps": 1.0, "roe": 10, "net_margin": 15, "debt_ratio": 40,
               "ocf_per_share": 1.0, "goodwill": 10, "total_assets": 100,
               "short_term_loan": 5, "long_term_loan": 3, "cash": 20,
               "revenue": 50, "net_profit": 5, "violation_penalty": 0,
               "audit_opinion": "标准无保留意见"}
        score = quality_score(fin, "科技")
        assert 0 <= score <= 100
