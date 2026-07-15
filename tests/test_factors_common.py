"""strategies/factors/score_utils.py 测试。"""

from strategies.factors.score_utils import pe_percentile, ScoringContext


def test_pe_percentile_undervalued():
    assert pe_percentile(10) == 15


def test_pe_percentile_reasonable():
    result = pe_percentile(20)
    assert 15 < result < 50


def test_pe_percentile_expensive():
    result = pe_percentile(30)
    assert 50 < result < 80


def test_pe_percentile_extreme():
    result = pe_percentile(100)
    assert result <= 95


def test_pe_percentile_negative():
    assert pe_percentile(-5) == 50
    assert pe_percentile(0) == 50


def test_scoring_context_creation():
    ctx = ScoringContext(
        quote={"price": 100, "pe": 20},
        fin={"eps": 5},
        features={"trend": 1, "ret20": 5},
        industry="消费",
        code="sh600519",
    )
    assert ctx.quote["price"] == 100
    assert ctx.industry == "消费"


def test_scoring_context_defaults():
    ctx = ScoringContext(quote={}, fin={}, features={})
    assert ctx.industry == "默认"
    assert ctx.code == ""
