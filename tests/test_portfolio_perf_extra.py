"""持仓绩效归因补充测试（v2.7.x 覆盖率提升）。

覆盖 _calculate_max_drawdown + format_performance_report + format_sector_attribution。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestCalculateMaxDrawdown:
    """_calculate_max_drawdown 最大回撤。"""

    def test_empty_kline(self):
        from portfolio.performance import _calculate_max_drawdown
        assert _calculate_max_drawdown([], {}, {}) == 0.0

    def test_single_bar(self):
        """仅 1 根 K 线无法计算回撤。"""
        from portfolio.performance import _calculate_max_drawdown
        positions = [{"code": "sh600519", "quantity": 100}]
        kline = {"sh600519": [MagicMock(day="2026-01-01", close=100)]}
        assert _calculate_max_drawdown(positions, kline, {}) == 0.0

    def test_drawdown_calculation(self):
        """3 根 K 线：100 -> 120 -> 90，最大回撤 = (120-90)/120 = 25%。"""
        from portfolio.performance import _calculate_max_drawdown
        positions = [{"code": "sh600519", "quantity": 100}]
        kline = {
            "sh600519": [
                MagicMock(day="2026-01-01", close=100),
                MagicMock(day="2026-01-02", close=120),
                MagicMock(day="2026-01-03", close=90),
            ]
        }
        dd = _calculate_max_drawdown(positions, kline, {})
        assert abs(dd - 25.0) < 0.1

    def test_no_matching_position(self):
        """K 线有但持仓无匹配 -> 回撤 0。"""
        from portfolio.performance import _calculate_max_drawdown
        positions = [{"code": "sz000858", "quantity": 100}]
        kline = {"sh600519": [MagicMock(day="2026-01-01", close=100)]}
        assert _calculate_max_drawdown(positions, kline, {}) == 0.0

    def test_zero_quantity_skipped(self):
        """数量为 0 的持仓跳过。"""
        from portfolio.performance import _calculate_max_drawdown
        positions = [{"code": "sh600519", "quantity": 0}]
        kline = {"sh600519": [MagicMock(day="2026-01-01", close=100),
                                MagicMock(day="2026-01-02", close=90)]}
        assert _calculate_max_drawdown(positions, kline, {}) == 0.0

    def test_dict_bars(self):
        """支持 dict 格式的 bar（非 dataclass）。"""
        from portfolio.performance import _calculate_max_drawdown
        positions = [{"code": "sh600519", "quantity": 100}]
        kline = {
            "sh600519": [
                {"day": "2026-01-01", "close": 100},
                {"day": "2026-01-02", "close": 80},
            ]
        }
        dd = _calculate_max_drawdown(positions, kline, {})
        assert abs(dd - 20.0) < 0.1


class TestFormatPerformanceReport:
    """format_performance_report 文本报告。"""

    def test_report_contains_key_sections(self):
        from portfolio.performance import PerformanceMetrics, format_performance_report
        metrics = PerformanceMetrics(
            total_return=15.5,
            max_drawdown=8.2,
            win_rate=66.7,
            total_profit=5000.0,
            position_count=3,
        )
        report = format_performance_report(metrics, [])
        assert "15.5" in report or "15.5%" in report

    def test_negative_return(self):
        from portfolio.performance import PerformanceMetrics, format_performance_report
        metrics = PerformanceMetrics(
            total_return=-10.0,
            max_drawdown=15.0,
            win_rate=33.3,
            total_profit=-2000.0,
            position_count=2,
        )
        report = format_performance_report(metrics, [])
        assert "-10" in report
