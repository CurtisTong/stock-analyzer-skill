"""hot_rank.py 热度榜测试。"""

import math
import pytest
from unittest.mock import MagicMock
from hot_rank import _filter_eligible, _hot_score


class TestHotScore:
    """_hot_score 热度分计算。"""

    def test_basic(self):
        """基础计算。"""
        score = _hot_score(1e8, 5.0)
        expected = 1e8 * math.log1p(5.0)
        assert abs(score - expected) < 1e-6

    def test_zero_turnover(self):
        """换手率为 0。"""
        score = _hot_score(1e8, 0)
        assert score == 0  # log1p(0) = 0

    def test_negative_turnover(self):
        """负换手率被 clamp 到 0。"""
        score = _hot_score(1e8, -5)
        assert score == 0

    def test_large_amount(self):
        """大成交额。"""
        score = _hot_score(1e10, 10)
        assert score > 0

    def test_monotonic(self):
        """成交额越大、换手率越高，分数越高。"""
        low = _hot_score(1e7, 1.0)
        high = _hot_score(1e8, 5.0)
        assert high > low


class TestFilterEligible:
    """_filter_eligible 过滤 ST/停牌/无成交。"""

    def _make_quote(self, name="测试", price=10.0, amount=1e6, turnover=1.0):
        q = MagicMock()
        q.name = name
        q.price = price
        q.amount = amount
        q.turnover = turnover
        return q

    def test_normal_stock(self):
        """正常股票通过。"""
        q = self._make_quote()
        result = _filter_eligible([q])
        assert len(result) == 1

    def test_st_filtered(self):
        """ST 股票被过滤。"""
        q = self._make_quote(name="*ST某某")
        assert _filter_eligible([q]) == []

    def test_delisted_filtered(self):
        """退市股票被过滤。"""
        q = self._make_quote(name="某某退")
        assert _filter_eligible([q]) == []

    def test_zero_price_filtered(self):
        """价格为 0 被过滤。"""
        q = self._make_quote(price=0)
        assert _filter_eligible([q]) == []

    def test_zero_amount_filtered(self):
        """成交额为 0 被过滤。"""
        q = self._make_quote(amount=0)
        assert _filter_eligible([q]) == []

    def test_zero_turnover_filtered(self):
        """换手率为 0 被过滤。"""
        q = self._make_quote(turnover=0)
        assert _filter_eligible([q]) == []

    def test_mixed(self):
        """混合场景：部分通过部分过滤。"""
        good = self._make_quote(name="正常", price=10, amount=1e6, turnover=1)
        bad_st = self._make_quote(name="*ST某某")
        bad_price = self._make_quote(price=0)
        result = _filter_eligible([good, bad_st, bad_price])
        assert len(result) == 1

    def test_empty_list(self):
        assert _filter_eligible([]) == []
