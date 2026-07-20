"""
apply_portfolio_constraints 测试（review#15）。
"""

import pytest


from screener import apply_portfolio_constraints  # noqa: E402


def _make_row(code, industry, score, trend="上升"):
    return {
        "code": code,
        "name": f"Stock-{code}",
        "industry": industry,
        "score": score,
        "trend": trend,
    }


class TestApplyPortfolioConstraints:
    """组合约束测试。"""

    def test_small_pool_keeps_all(self):
        """5 只池时不强制板块集中度（review#15 核心修复）。"""
        rows = [
            _make_row("sh600000", "银行", 90),
            _make_row("sh600001", "银行", 80),
            _make_row("sh600002", "银行", 70),
            _make_row("sh600003", "银行", 60),
            _make_row("sh600004", "银行", 50),
        ]
        result = apply_portfolio_constraints(rows, sector_cap=0.30)
        assert len(result) == 5  # 全部保留

    def test_large_pool_enforces_sector_cap(self):
        """20 只池时单板块最多 30% × 20 = 6 只。"""
        rows = [_make_row(f"sh{600000+i}", "银行", 100 - i) for i in range(15)]
        rows += [_make_row(f"sh{700000+i}", "科技", 50 - i) for i in range(5)]
        result = apply_portfolio_constraints(rows, sector_cap=0.30)
        # 银行最多 6 只（30% × 20 = 6）
        bank_count = sum(1 for r in result if r["industry"] == "银行")
        tech_count = sum(1 for r in result if r["industry"] == "科技")
        assert bank_count == 6
        assert tech_count == 5

    def test_trend_down_penalty(self):
        """下降趋势得分打 0.7 折。"""
        rows = [
            _make_row("sh600000", "科技", 80, "下降"),
            _make_row("sh600001", "银行", 70, "上升"),
        ]
        result = apply_portfolio_constraints(rows, sector_cap=0.30)
        # 下降趋势 80 * 0.7 = 56
        down_row = next(r for r in result if r["code"] == "sh600000")
        assert down_row["score"] == 56.0
        # 上升趋势 70 不变
        up_row = next(r for r in result if r["code"] == "sh600001")
        assert up_row["score"] == 70.0
        # 排序后下降股应排在上升股后
        assert result[0]["code"] == "sh600001"
        assert result[1]["code"] == "sh600000"

    def test_empty_pool(self):
        """空池不报错。"""
        assert apply_portfolio_constraints([]) == []

    def test_boundary_pool_9_stocks(self):
        """9 只池（边界 < 10）不限制。"""
        rows = [_make_row(f"sh{600000+i}", "银行", 100 - i) for i in range(9)]
        result = apply_portfolio_constraints(rows, sector_cap=0.30)
        assert len(result) == 9  # 全部保留
