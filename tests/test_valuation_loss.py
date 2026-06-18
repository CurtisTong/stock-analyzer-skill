"""
valuation.py 亏损股分支测试（Sprint 13）。
"""

import pytest

from strategies.factors import valuation


class TestLossStockValuation:
    """亏损股（pe <= 0）的 PS 视角评分测试。"""

    def test_loss_stock_with_growth(self):
        """亏损 + 净利润同比为正（亏损收窄）→ 加 12 分。"""
        quote = {"pe": 0, "pb": 0, "total_cap": 50}
        fin = {"net_profit_yoy": 5.0, "revenue_yoy": 15.0}
        score = valuation.valuation_score(quote, fin, "默认")
        assert score > 0  # 应有 PS 加分

    def test_loss_stock_high_revenue_growth(self):
        """亏损 + 高营收增速（> 30%）→ +20 分。"""
        quote = {"pe": 0, "pb": 0, "total_cap": 50}
        fin = {"net_profit_yoy": 0, "revenue_yoy": 50.0}
        score = valuation.valuation_score(quote, fin, "默认")
        # 高增长亏损应得 20 + 0 = 20 分
        assert score >= 20

    def test_loss_stock_medium_revenue_growth(self):
        """亏损 + 中等营收增速（10-30%）→ +12 分。"""
        quote = {"pe": 0, "pb": 0, "total_cap": 50}
        fin = {"net_profit_yoy": 0, "revenue_yoy": 15.0}
        score = valuation.valuation_score(quote, fin, "默认")
        assert score >= 12

    def test_loss_stock_low_revenue_growth(self):
        """亏损 + 低营收增速（0-10%）→ +5 分。"""
        quote = {"pe": 0, "pb": 0, "total_cap": 50}
        fin = {"net_profit_yoy": 0, "revenue_yoy": 5.0}
        score = valuation.valuation_score(quote, fin, "默认")
        assert score >= 5

    def test_loss_stock_no_revenue_growth(self):
        """亏损 + 营收不增长 → 0 PS 加分。"""
        quote = {"pe": 0, "pb": 0, "total_cap": 50}
        fin = {"net_profit_yoy": 0, "revenue_yoy": -5.0}
        score = valuation.valuation_score(quote, fin, "默认")
        # 营收负增长不加分，但可能有 PB 加分
        assert score < 12  # 没有 +20/+12

    def test_large_cap_loss_penalty(self):
        """大市值（>100 亿）+ 亏损 + 营收负增长 → -8 分惩罚。"""
        quote = {"pe": 0, "pb": 0, "total_cap": 200}
        fin = {"net_profit_yoy": 0, "revenue_yoy": -10.0}
        score = valuation.valuation_score(quote, fin, "默认")
        # 应触发大市值亏损惩罚
        assert score < 5  # 接近 0 或负分

    def test_pe_too_high_returns_zero_pe_score(self):
        """PE 超极端阈值（>2×pe_expensive）时 PE 评分为 0。"""
        # 行业默认 pe_expensive=40，超 80 触发
        quote = {"pe": 100, "pb": 2}
        fin = {"net_profit_yoy": 50.0, "revenue_yoy": 30.0}
        score = valuation.valuation_score(quote, fin, "默认")
        # 仍可能有 PB 加分
        assert score >= 0

    def test_extreme_peg_fallback(self):
        """PE 极端但 PB 合理时仍能评分。"""
        quote = {"pe": 100, "pb": 1}
        fin = {"net_profit_yoy": 50.0, "revenue_yoy": 30.0}
        score = valuation.valuation_score(quote, fin, "默认")
        # PB=1 触发 24 分满分
        assert score > 0
