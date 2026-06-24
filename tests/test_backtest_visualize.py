"""回测可视化模块测试。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from backtest.visualize import (
    render_return_curve,
    render_drawdown_chart,
    render_backtest_summary,
)


class TestRenderReturnCurve:
    """render_return_curve 函数测试。"""

    def test_empty_returns(self):
        """空收益列表返回提示。"""
        result = render_return_curve([])
        assert "无收益数据" in result

    def test_positive_returns(self):
        """正收益曲线。"""
        returns = [1.0, 2.0, 1.5, 3.0]
        result = render_return_curve(returns, width=10, height=5)
        assert "累计收益曲线" in result
        assert "%" in result

    def test_negative_returns(self):
        """负收益曲线。"""
        returns = [-1.0, -2.0, -1.5, -3.0]
        result = render_return_curve(returns, width=10, height=5)
        assert "累计收益曲线" in result

    def test_mixed_returns(self):
        """混合收益曲线。"""
        returns = [1.0, -2.0, 3.0, -1.0, 2.0]
        result = render_return_curve(returns, width=10, height=5)
        assert "█" in result  # 曲线字符
        assert "─" in result  # 零线

    def test_single_return(self):
        """单期收益。"""
        result = render_return_curve([5.0], width=10, height=5)
        assert "累计收益曲线" in result

    def test_custom_title(self):
        """自定义标题。"""
        result = render_return_curve([1.0, 2.0], title="测试图表")
        assert "测试图表" in result


class TestRenderDrawdownChart:
    """render_drawdown_chart 函数测试。"""

    def test_empty_returns(self):
        """空收益列表返回提示。"""
        result = render_drawdown_chart([])
        assert "无收益数据" in result

    def test_no_drawdown(self):
        """无回撤（持续上涨）。"""
        returns = [1.0, 1.0, 1.0, 1.0]
        result = render_drawdown_chart(returns, width=10, height=5)
        assert "回撤图" in result
        assert "最大回撤: 0.00%" in result

    def test_with_drawdown(self):
        """有回撤。"""
        returns = [1.0, -3.0, 1.0, 1.0]
        result = render_drawdown_chart(returns, width=10, height=5)
        assert "回撤图" in result
        assert "最大回撤" in result

    def test_late_drawdown(self):
        """后期回撤。"""
        returns = [1.0, 1.0, 1.0, -5.0]
        result = render_drawdown_chart(returns, width=10, height=5)
        assert "回撤图" in result


class TestRenderBacktestSummary:
    """render_backtest_summary 函数测试。"""

    def test_error_report(self):
        """错误报告显示失败原因。"""
        report = {"error": "数据不足"}
        result = render_backtest_summary(report)
        assert "❌" in result
        assert "数据不足" in result

    def test_normal_report(self):
        """正常报告。"""
        report = {
            "strategy": "balanced",
            "total_return_pct": 15.5,
            "win_rate_pct": 60.0,
            "sharpe_ratio": 1.2,
            "max_drawdown_pct": 8.5,
            "calmar_ratio": 1.8,
            "profit_loss_ratio": 1.5,
            "total_trades": 50,
            "rounds": 10,
            "round_details": [{"returns": [1.0, 2.0, -1.0, 3.0, 0.5]}],
        }
        result = render_backtest_summary(report)
        assert "balanced" in result
        assert "+15.50%" in result
        assert "60.0%" in result
        assert "1.20" in result
        assert "8.50%" in result

    def test_negative_return(self):
        """负收益报告。"""
        report = {
            "strategy": "defensive",
            "total_return_pct": -5.2,
            "win_rate_pct": 40.0,
            "sharpe_ratio": -0.5,
            "max_drawdown_pct": 12.0,
            "calmar_ratio": -0.4,
            "profit_loss_ratio": 0.8,
            "total_trades": 30,
            "rounds": 6,
            "round_details": [{"returns": [-1.0, -2.0, 1.0, -3.0, 2.0, -1.2]}],
        }
        result = render_backtest_summary(report)
        assert "defensive" in result
        assert "-5.20%" in result
        assert "🔴" in result

    def test_no_round_details(self):
        """无详细数据时使用平均收益。"""
        report = {
            "strategy": "balanced",
            "total_return_pct": 10.0,
            "win_rate_pct": 50.0,
            "sharpe_ratio": 1.0,
            "max_drawdown_pct": 5.0,
            "calmar_ratio": 2.0,
            "profit_loss_ratio": 1.2,
            "total_trades": 20,
            "rounds": 4,
            "avg_return_pct": 2.5,
        }
        result = render_backtest_summary(report)
        assert "balanced" in result
