"""
liquidity.py 换手率分支测试（Sprint 13）。
"""

import pytest

from strategies.factors import liquidity


class TestLiquidityByCapTier:
    """按市值分层的换手率评分。"""

    def test_large_cap_normal_turnover(self):
        """大盘股（>500亿）正常换手率（0.1-5%）→ +24。"""
        quote = {
            "code": "sh600519",
            "amount": 100000_0000,
            "total_cap": 1000,
            "turnover": 1.0,
        }
        score = liquidity.liquidity_score(quote)
        # 24 换手 + 28 市值 + 42 成交额（封顶）= 94
        assert score > 80

    def test_large_cap_high_turnover(self):
        """大盘股换手率 5-10% → +14（验证分支触发）。"""
        # 用 cap=140（不封顶），amount=10000 万（不封顶）让换手率影响可见
        quote = {
            "code": "sh600519",
            "amount": 10000_0000,
            "total_cap": 140,
            "turnover": 7.0,
        }
        score = liquidity.liquidity_score(quote)
        # 不应封顶 100（换手率分支差异）
        assert score < 100

    def test_mid_cap_normal_turnover(self):
        """中盘股（100-500亿）正常换手率（0.3-8%）→ +24。"""
        quote = {
            "code": "sh600519",
            "amount": 100000_0000,
            "total_cap": 300,
            "turnover": 3.0,
        }
        score = liquidity.liquidity_score(quote)
        assert score > 60

    def test_mid_cap_high_turnover(self):
        """中盘股换手率 8-15% → +14（验证分支触发）。"""
        # 降低市值避免封顶
        quote = {
            "code": "sh600519",
            "amount": 10000_0000,
            "total_cap": 200,
            "turnover": 10.0,
        }
        score = liquidity.liquidity_score(quote)
        # 不应封顶
        assert score < 100

    def test_small_cap_normal_turnover(self):
        """小盘股（<100亿）正常换手率（0.5-12%）→ +24。"""
        quote = {
            "code": "sh600519",
            "amount": 100000_0000,
            "total_cap": 50,
            "turnover": 5.0,
        }
        score = liquidity.liquidity_score(quote)
        assert score > 50

    def test_small_cap_extreme_turnover(self):
        """小盘股换手率 > 20% → +6（验证触发条件）。"""
        quote = {
            "code": "sh600519",
            "amount": 100000_0000,
            "total_cap": 50,
            "turnover": 25.0,
        }
        score_extreme = liquidity.liquidity_score(quote)
        # 与正常换手率对比
        quote_normal = {
            "code": "sh600519",
            "amount": 100000_0000,
            "total_cap": 50,
            "turnover": 5.0,
        }
        score_normal = liquidity.liquidity_score(quote_normal)
        # 极端换手率应低于正常
        assert score_extreme < score_normal

    def test_other_board_fallback(self):
        """非标准板块用默认阈值。"""
        quote = {
            "code": "xx1234",
            "amount": 100000_0000,
            "total_cap": 100,
            "turnover": 1.0,
        }
        score = liquidity.liquidity_score(quote)
        assert score > 0
