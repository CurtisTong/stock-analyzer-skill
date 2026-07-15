"""portfolio/performance.py 覆盖测试（纯数据）。

覆盖 format_performance_report、calculate_sector_attribution、
format_sector_attribution 更多分支、PerformanceMetrics/PositionContribution/
SectorAttribution 的 to_dict/__post_init__。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from portfolio.performance import (
    PerformanceMetrics,
    PositionContribution,
    SectorAttribution,
    _calculate_max_drawdown,
    calculate_portfolio_metrics,
    calculate_position_contribution,
    calculate_sector_attribution,
    format_performance_report,
    format_sector_attribution,
)


class TestPerformanceMetricsToDict:
    def test_to_dict_returns_copy(self):
        m = PerformanceMetrics(total_return=12.5, position_count=3)
        d = m.to_dict()
        assert d["total_return"] == 12.5
        assert d["position_count"] == 3
        d["total_return"] = 999
        assert m.total_return == 12.5  # 原对象未变


class TestPositionContributionToDict:
    def test_to_dict_returns_copy(self):
        c = PositionContribution(code="sh600519", name="茅台", profit=1000.0)
        d = c.to_dict()
        assert d["code"] == "sh600519"
        assert d["profit"] == 1000.0


class TestCalculatePositionContribution:
    def test_empty_positions(self):
        assert calculate_position_contribution([], {}) == []

    def test_zero_total_market_value(self):
        """quantity=0 时 total_market_value=0，weight/contribution 为 0。"""
        positions = [{"code": "sh600519", "name": "茅台", "cost": 100, "quantity": 0}]
        quotes = {"sh600519": {"price": 0}}
        result = calculate_position_contribution(positions, quotes)
        assert len(result) == 1
        assert result[0].weight == 0
        assert result[0].contribution == 0

    def test_sorted_by_contribution_desc(self):
        positions = [
            {"code": "sh600519", "name": "A", "cost": 10, "quantity": 100},
            {"code": "sh600001", "name": "B", "cost": 10, "quantity": 100},
        ]
        quotes = {
            "sh600519": {"price": 15},  # 盈利
            "sh600001": {"price": 8},  # 亏损
        }
        result = calculate_position_contribution(positions, quotes)
        assert result[0].code == "sh600519"  # 贡献大的在前
        assert result[1].code == "sh600001"

    def test_zero_cost_profit_pct(self):
        """cost=0 时 profit_pct=0。"""
        positions = [{"code": "sh600519", "name": "A", "cost": 0, "quantity": 100}]
        quotes = {"sh600519": {"price": 10}}
        result = calculate_position_contribution(positions, quotes)
        assert result[0].profit_pct == 0


class TestCalculatePortfolioMetrics:
    def test_no_kline_data(self):
        positions = [{"code": "sh600519", "name": "A", "cost": 10, "quantity": 100}]
        quotes = {"sh600519": {"price": 12}}
        m = calculate_portfolio_metrics(positions, quotes)
        assert m.max_drawdown == 0.0
        assert m.position_count == 1
        assert m.total_return == 20.0

    def test_empty_positions(self):
        m = calculate_portfolio_metrics([], {})
        assert m.win_rate == 0
        assert m.position_count == 0


class TestCalculateMaxDrawdown:
    def test_empty_kline(self):
        assert _calculate_max_drawdown([], {}, {}) == 0.0

    def test_bar_dict_format(self):
        """bar 为 dict 格式（含 day/close）。"""
        positions = [{"code": "sh600519", "quantity": 100}]
        kline = {
            "sh600519": [
                {"day": "2025-01-01", "close": 10},
                {"day": "2025-01-02", "close": 12},
                {"day": "2025-01-03", "close": 8},  # 回撤
            ]
        }
        dd = _calculate_max_drawdown(positions, kline, {})
        # peak=1200, valley=800 -> (1200-800)/1200 = 33.33%
        assert dd == pytest.approx(33.33, abs=0.1)

    def test_bar_object_format(self):
        """bar 为对象格式（含 .day/.close 属性）。"""

        class _Bar:
            def __init__(self, day, close):
                self.day = day
                self.close = close

        positions = [{"code": "sh600519", "quantity": 100}]
        kline = {
            "sh600519": [
                _Bar("2025-01-01", 10),
                _Bar("2025-01-02", 15),
                _Bar("2025-01-03", 9),
            ]
        }
        dd = _calculate_max_drawdown(positions, kline, {})
        assert dd > 0

    def test_single_bar_no_drawdown(self):
        positions = [{"code": "sh600519", "quantity": 100}]
        kline = {"sh600519": [{"day": "2025-01-01", "close": 10}]}
        assert _calculate_max_drawdown(positions, kline, {}) == 0.0

    def test_zero_quantity_skipped(self):
        positions = [{"code": "sh600519", "quantity": 0}]
        kline = {"sh600519": [{"day": "2025-01-01", "close": 10}]}
        assert _calculate_max_drawdown(positions, kline, {}) == 0.0

    def test_position_not_found_skipped(self):
        positions = [{"code": "sh600519", "quantity": 100}]
        kline = {"sh000001": [{"day": "2025-01-01", "close": 10}]}
        assert _calculate_max_drawdown(positions, kline, {}) == 0.0


class TestFormatPerformanceReport:
    def test_empty_contributions(self):
        m = PerformanceMetrics(total_return=10.0, total_profit=1000, position_count=0)
        report = format_performance_report(m, [])
        assert "持仓绩效报告" in report
        assert "总收益率: **10.0%**" in report

    def test_with_contributions(self):
        m = PerformanceMetrics(total_return=10.0, total_profit=1000, position_count=2)
        contributions = [
            PositionContribution(
                code="sh600519",
                name="茅台",
                cost=100,
                current_price=120,
                profit=2000,
                profit_pct=20.0,
                weight=60.0,
                contribution=12.0,
            ),
            PositionContribution(
                code="sh600001",
                name="浦发",
                cost=10,
                current_price=8,
                profit=-200,
                profit_pct=-20.0,
                weight=40.0,
                contribution=-8.0,
            ),
        ]
        report = format_performance_report(m, contributions)
        assert "茅台" in report
        assert "最大贡献" in report
        assert "最大拖累" in report  # worst.contribution < 0

    def test_no_drag_when_all_positive(self):
        m = PerformanceMetrics(total_return=10.0, position_count=1)
        contributions = [
            PositionContribution(
                code="sh600519",
                name="茅台",
                profit=2000,
                profit_pct=20.0,
                contribution=12.0,
            ),
        ]
        report = format_performance_report(m, contributions)
        assert "最大拖累" not in report


class TestSectorAttribution:
    def test_post_init_creates_positions_list(self):
        sa = SectorAttribution(sector="银行")
        assert sa.positions == []

    def test_to_dict_serializes_positions(self):
        c = PositionContribution(code="sh600519", name="茅台")
        sa = SectorAttribution(sector="白酒", positions=[c])
        d = sa.to_dict()
        assert d["sector"] == "白酒"
        assert d["positions"][0]["code"] == "sh600519"

    def test_to_dict_with_raw_dict_positions(self):
        sa = SectorAttribution(sector="银行", positions=[{"code": "sh600001"}])
        d = sa.to_dict()
        assert d["positions"][0] == {"code": "sh600001"}

    def test_calculate_sector_attribution_empty(self):
        assert calculate_sector_attribution([], {}) == []

    def test_calculate_sector_attribution_zero_value(self):
        positions = [{"code": "sh600519", "name": "A", "cost": 10, "quantity": 0}]
        quotes = {"sh600519": {"price": 0}}
        assert calculate_sector_attribution(positions, quotes) == []

    def test_calculate_sector_attribution_with_industry(self):
        positions = [
            {
                "code": "sh600519",
                "name": "茅台",
                "cost": 100,
                "quantity": 100,
                "industry": "白酒",
            },
            {
                "code": "sh000858",
                "name": "五粮液",
                "cost": 100,
                "quantity": 100,
                "industry": "白酒",
            },
            {
                "code": "sh600036",
                "name": "招行",
                "cost": 30,
                "quantity": 100,
                "industry": "银行",
            },
        ]
        quotes = {
            "sh600519": {"price": 120},
            "sh000858": {"price": 110},
            "sh600036": {"price": 35},
        }
        result = calculate_sector_attribution(positions, quotes)
        assert len(result) == 2  # 白酒 + 银行
        sectors = [r.sector for r in result]
        assert "白酒" in sectors
        assert "银行" in sectors

    def test_calculate_sector_attribution_no_industry_falls_to_other(self):
        positions = [{"code": "sh600519", "name": "A", "cost": 10, "quantity": 100}]
        quotes = {"sh600519": {"price": 12}}
        result = calculate_sector_attribution(positions, quotes)
        assert result[0].sector == "其他"

    def test_calculate_sector_attribution_empty_code_skipped(self):
        positions = [
            {"code": "", "name": "A", "cost": 10, "quantity": 100},
            {
                "code": "sh600519",
                "name": "B",
                "cost": 10,
                "quantity": 100,
                "industry": "白酒",
            },
        ]
        quotes = {"sh600519": {"price": 12}}
        result = calculate_sector_attribution(positions, quotes)
        assert len(result) == 1


class TestFormatSectorAttribution:
    def test_empty(self):
        assert format_sector_attribution([]) == "暂无持仓数据，无法生成行业归因。"

    def test_basic_format(self):
        attributions = [
            SectorAttribution(
                sector="白酒",
                weight=60.0,
                contribution=12.0,
                profit_pct=20.0,
                position_count=2,
            ),
            SectorAttribution(
                sector="银行",
                weight=40.0,
                contribution=-4.0,
                profit_pct=-10.0,
                position_count=1,
            ),
        ]
        report = format_sector_attribution(attributions)
        assert "行业归因分析" in report
        assert "白酒" in report
        assert "最大贡献行业" in report
        assert "最大拖累行业" in report

    def test_no_drag_when_all_positive(self):
        attributions = [
            SectorAttribution(
                sector="白酒", weight=60.0, contribution=12.0, profit_pct=20.0
            ),
        ]
        report = format_sector_attribution(attributions)
        assert "最大拖累行业" not in report
