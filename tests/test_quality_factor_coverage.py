import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestEarningsQualityScore:
    def test_positive_eps(self):
        from strategies.factors.quality import _earnings_quality_score

        fin = {
            "net_margin": 20,
            "roe": 15,
            "debt_ratio": 30,
            "ocf_per_share": 2.0,
            "eps": 2.0,
        }
        score = _earnings_quality_score(fin, 2.0)
        assert 0 <= score <= 100

    def test_negative_eps(self):
        from strategies.factors.quality import _earnings_quality_score

        fin = {"net_margin": -10, "roe": -5, "debt_ratio": 60}
        score = _earnings_quality_score(fin, -1.0)
        assert score < 50

    def test_missing_fields(self):
        from strategies.factors.quality import _earnings_quality_score

        score = _earnings_quality_score({}, 1.0)
        assert 0 <= score <= 100


class TestESGScore:
    def test_with_esg_data(self):
        from strategies.factors.quality import _esg_score

        fin = {"violation_penalty": 0, "audit_opinion": "标准无保留意见"}
        score = _esg_score(fin)
        assert 0 <= score <= 100

    def test_violation(self):
        from strategies.factors.quality import _esg_score

        fin = {"violation_penalty": 1000000, "audit_opinion": "保留意见"}
        score = _esg_score(fin)
        assert score < 50


class TestRedFlagScore:
    def test_clean_company(self):
        from strategies.factors.quality import _a_stock_red_flag_score

        fin = {
            "goodwill": 0,
            "total_assets": 100,
            "short_term_loan": 5,
            "long_term_loan": 3,
            "cash": 20,
            "revenue": 50,
            "net_profit": 5,
            "ocf": 6,
            "related_transaction": 2,
        }
        score = _a_stock_red_flag_score(fin)
        assert score >= 0

    def test_red_flags(self):
        from strategies.factors.quality import _a_stock_red_flag_score

        fin = {
            "goodwill": 80,
            "total_assets": 100,
            "short_term_loan": 50,
            "long_term_loan": 30,
            "cash": 5,
            "revenue": 10,
            "net_profit": 1,
            "ocf": -5,
        }
        score = _a_stock_red_flag_score(fin)
        assert isinstance(score, (int, float, dict))


class TestQualityScore:
    def test_overall(self):
        from strategies.factors.quality import quality_score

        fin = {
            "eps": 2.0,
            "roe": 15,
            "net_margin": 20,
            "debt_ratio": 30,
            "ocf_per_share": 2.0,
            "goodwill": 5,
            "total_assets": 100,
            "short_term_loan": 5,
            "long_term_loan": 3,
            "cash": 20,
            "revenue": 50,
            "net_profit": 5,
            "violation_penalty": 0,
            "audit_opinion": "标准无保留意见",
        }
        score = quality_score(fin)
        assert 0 <= score <= 100
