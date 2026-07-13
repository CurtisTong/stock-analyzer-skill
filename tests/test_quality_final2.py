import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestEarningsQualityMore:
    def test_high_quality(self):
        from strategies.factors.quality import _earnings_quality_score
        fin = {"net_margin": 30, "roe": 25, "debt_ratio": 20, "ocf_per_share": 3.0}
        score = _earnings_quality_score(fin, 3.0)
        assert score > 60

    def test_low_quality(self):
        from strategies.factors.quality import _earnings_quality_score
        fin = {"net_margin": 2, "roe": 3, "debt_ratio": 70, "ocf_per_share": 0.1}
        score = _earnings_quality_score(fin, 0.1)
        assert score < 50

class TestESGMore:
    def test_clean(self):
        from strategies.factors.quality import _esg_score
        fin = {"violation_penalty": 0, "audit_opinion": "标准无保留意见"}
        score = _esg_score(fin)
        assert score > 50

    def test_no_data(self):
        from strategies.factors.quality import _esg_score
        score = _esg_score({})
        assert 0 <= score <= 100

class TestQualityScoreIndustries:
    def test_medical(self):
        from strategies.factors.quality import quality_score
        fin = {"eps": 1.0, "roe": 10, "net_margin": 15, "debt_ratio": 40,
               "ocf_per_share": 1.0, "goodwill": 10, "total_assets": 100,
               "short_term_loan": 5, "long_term_loan": 3, "cash": 20,
               "revenue": 50, "net_profit": 5, "violation_penalty": 0,
               "audit_opinion": "标准无保留意见"}
        score = quality_score(fin, "医药")
        assert 0 <= score <= 100
