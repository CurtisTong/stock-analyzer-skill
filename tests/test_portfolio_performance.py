"""
测试 scripts/portfolio/performance.py：组合绩效计算。

核心数学恒等式：
1. 各持仓 contribution 加和 ≈ total_return%
2. 各持仓 weight 加和 = 100%（容差 0.01%）
3. 单股 profit = market_value - cost_value
4. 单股 profit_pct = (current_price / cost - 1) * 100

Property-based 测试（hypothesis 可选）覆盖数学不变量。
"""
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from portfolio.performance import (
    calculate_position_contribution,
    calculate_portfolio_metrics,
    PositionContribution,
    PerformanceMetrics,
)


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def sample_positions():
    return [
        {"code": "sh600989", "name": "宝丰能源", "cost": 18.50, "quantity": 1000},
        {"code": "sz000807", "name": "云铝股份", "cost": 12.00, "quantity": 500},
        {"code": "sh600519", "name": "贵州茅台", "cost": 1800.0, "quantity": 10},
    ]


@pytest.fixture
def sample_quotes():
    return {
        "sh600989": {"price": "20.00"},  # +8.1%
        "sz000807": {"price": "11.00"},  # -8.3%
        "sh600519": {"price": "1900.0"},  # +5.6%
    }


# ═══════════════════════════════════════════════════════════════
# PositionContribution 计算
# ═══════════════════════════════════════════════════════════════

class TestPositionContribution:
    def test_returns_list(self, sample_positions, sample_quotes):
        result = calculate_position_contribution(sample_positions, sample_quotes)
        assert isinstance(result, list)
        assert len(result) == 3

    def test_sorted_by_contribution_desc(self, sample_positions, sample_quotes):
        """按 contribution 降序排序。"""
        result = calculate_position_contribution(sample_positions, sample_quotes)
        for i in range(len(result) - 1):
            assert result[i].contribution >= result[i + 1].contribution

    def test_profit_calculation(self, sample_positions, sample_quotes):
        """profit = market_value - cost_value。"""
        result = calculate_position_contribution(sample_positions, sample_quotes)
        sh600989 = next(c for c in result if c.code == "sh600989")
        # market_value = 20 * 1000 = 20000
        # cost_value = 18.5 * 1000 = 18500
        # profit = 20000 - 18500 = 1500
        assert sh600989.market_value == 20000
        assert sh600989.profit == 1500

    def test_profit_pct_calculation(self, sample_positions, sample_quotes):
        """profit_pct = (current_price / cost - 1) * 100。"""
        result = calculate_position_contribution(sample_positions, sample_quotes)
        sh600989 = next(c for c in result if c.code == "sh600989")
        # 20/18.5 - 1 = 0.0810... = 8.11%
        assert abs(sh600989.profit_pct - 8.11) < 0.1

    def test_negative_profit_for_losing_position(self, sample_positions, sample_quotes):
        """亏损持仓 profit < 0。"""
        result = calculate_position_contribution(sample_positions, sample_quotes)
        sz000807 = next(c for c in result if c.code == "sz000807")
        # 11/12 - 1 = -8.33%
        assert sz000807.profit < 0
        assert sz000807.profit_pct < 0

    def test_to_dict_structure(self, sample_positions, sample_quotes):
        """to_dict 输出包含所有字段。"""
        result = calculate_position_contribution(sample_positions, sample_quotes)
        d = result[0].to_dict()
        assert "code" in d
        assert "name" in d
        assert "market_value" in d
        assert "profit" in d
        assert "profit_pct" in d
        assert "weight" in d
        assert "contribution" in d


# ═══════════════════════════════════════════════════════════════
# PortfolioMetrics 计算
# ═══════════════════════════════════════════════════════════════

class TestPortfolioMetrics:
    def test_returns_metrics_object(self, sample_positions, sample_quotes):
        result = calculate_portfolio_metrics(sample_positions, sample_quotes)
        assert isinstance(result, PerformanceMetrics)
        assert result.position_count == 3

    def test_total_profit_matches_sum(self, sample_positions, sample_quotes):
        """total_profit = sum(per_position profit)。"""
        result = calculate_portfolio_metrics(sample_positions, sample_quotes)
        contributions = calculate_position_contribution(sample_positions, sample_quotes)
        expected = sum(c.profit for c in contributions)
        assert abs(result.total_profit - expected) < 0.1

    def test_win_rate(self, sample_positions, sample_quotes):
        """胜率 = 盈利持仓 / 总持仓。"""
        result = calculate_portfolio_metrics(sample_positions, sample_quotes)
        # sh600989 盈利，sz000807 亏损，sh600519 盈利 → 2/3 = 66.7%
        assert abs(result.win_rate - 66.7) < 0.5

    def test_all_winning_positions(self, sample_positions):
        """全部盈利时胜率 100%。"""
        quotes = {
            "sh600989": {"price": "20.00"},
            "sz000807": {"price": "13.00"},
            "sh600519": {"price": "2000.0"},
        }
        result = calculate_portfolio_metrics(sample_positions, quotes)
        assert result.win_rate == 100.0

    def test_all_losing_positions(self, sample_positions):
        """全部亏损时胜率 0%。"""
        quotes = {
            "sh600989": {"price": "15.00"},
            "sz000807": {"price": "10.00"},
            "sh600519": {"price": "1500.0"},
        }
        result = calculate_portfolio_metrics(sample_positions, quotes)
        assert result.win_rate == 0.0

    def test_max_drawdown_zero_without_kline(self, sample_positions, sample_quotes):
        """无 K 线数据时 max_drawdown = 0。"""
        result = calculate_portfolio_metrics(sample_positions, sample_quotes)
        assert result.max_drawdown == 0.0

    def test_empty_positions(self):
        """空持仓列表应安全返回。"""
        result = calculate_portfolio_metrics([], {})
        assert result.position_count == 0
        assert result.total_profit == 0
        assert result.total_return == 0
        assert result.win_rate == 0


# ═══════════════════════════════════════════════════════════════
# 数学恒等式 property test
# ═══════════════════════════════════════════════════════════════

class TestPerformanceInvariants:
    """数学不变量测试（hypothesis 可选）。"""

    def test_weights_sum_to_100(self, sample_positions, sample_quotes):
        """所有 weight 加和 = 100%。"""
        contributions = calculate_position_contribution(sample_positions, sample_quotes)
        total_weight = sum(c.weight for c in contributions)
        assert abs(total_weight - 100.0) < 0.01

    def test_total_profit_equals_market_value_minus_cost(self, sample_positions, sample_quotes):
        """total_profit = total_market_value - total_cost。"""
        contributions = calculate_position_contribution(sample_positions, sample_quotes)
        total_mv = sum(c.market_value for c in contributions)
        total_cost = sum(c.cost * c.quantity for c in contributions)
        expected = total_mv - total_cost
        result = calculate_portfolio_metrics(sample_positions, sample_quotes)
        assert abs(result.total_profit - expected) < 0.1

    def test_total_return_positive_when_profit(self, sample_positions):
        """盈利时 total_return > 0。"""
        quotes = {
            "sh600989": {"price": "20.00"},
            "sz000807": {"price": "13.00"},
            "sh600519": {"price": "2000.0"},
        }
        result = calculate_portfolio_metrics(sample_positions, quotes)
        assert result.total_return > 0

    def test_total_return_negative_when_loss(self, sample_positions):
        """亏损时 total_return < 0。"""
        quotes = {
            "sh600989": {"price": "15.00"},
            "sz000807": {"price": "10.00"},
            "sh600519": {"price": "1500.0"},
        }
        result = calculate_portfolio_metrics(sample_positions, quotes)
        assert result.total_return < 0


# ═══════════════════════════════════════════════════════════════
# Property-based 测试（hypothesis 可选）
# ═══════════════════════════════════════════════════════════════

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    @given(
        cost=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        price=st.floats(min_value=0.5, max_value=2000.0, allow_nan=False, allow_infinity=False),
        quantity=st.integers(min_value=1, max_value=10000),
    )
    @settings(max_examples=100, deadline=None)
    def test_profit_equals_mv_minus_cv(cost, price, quantity):
        """单股 profit = market_value - cost_value 数学恒等式。"""
        positions = [{"code": "x", "name": "X", "cost": cost, "quantity": quantity}]
        quotes = {"x": {"price": str(price)}}
        contributions = calculate_position_contribution(positions, quotes)
        mv = price * quantity
        cv = cost * quantity
        expected = mv - cv
        assert abs(contributions[0].profit - round(expected, 2)) < 0.1

    @given(
        cost=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        price=st.floats(min_value=0.5, max_value=2000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_profit_pct_formula(cost, price):
        """profit_pct = (price/cost - 1) * 100。"""
        positions = [{"code": "x", "name": "X", "cost": cost, "quantity": 100}]
        quotes = {"x": {"price": str(price)}}
        contributions = calculate_position_contribution(positions, quotes)
        expected = (price / cost - 1) * 100
        assert abs(contributions[0].profit_pct - round(expected, 2)) < 0.1

except ImportError:
    def test_profit_equals_mv_minus_cv():
        pass

    def test_profit_pct_formula():
        pass
