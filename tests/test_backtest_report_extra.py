"""strategies/patterns/backtest_report.py 补充测试：统计/图表/报告生成（纯数据测试）。"""

import math
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from strategies.patterns.backtest_report import (
    calculate_advanced_stats,
    generate_ascii_chart,
    generate_return_distribution,
    generate_trade_timeline,
    generate_backtest_report,
    generate_comparison_report,
    load_kline_data,
)


# ═══════════════════════════════════════════════════════════════
# calculate_advanced_stats
# ═══════════════════════════════════════════════════════════════


def _make_trade(return_pct, signal="MA金叉+放量2.5x"):
    return {
        "buy_date": "2024-01-01",
        "buy_price": 10.0,
        "sell_date": "2024-01-06",
        "sell_price": 10.0 * (1 + return_pct / 100),
        "return_pct": return_pct,
        "signal": signal,
    }


class TestCalculateAdvancedStats:
    def test_empty_trades(self):
        assert calculate_advanced_stats([]) == {}

    def test_single_trade(self):
        trades = [_make_trade(5)]
        stats = calculate_advanced_stats(trades)
        assert stats["total_trades"] == 1
        assert stats["win_count"] == 1
        assert stats["win_rate"] == 100.0
        assert stats["win_rate"] == 100.0

    def test_all_wins(self):
        trades = [_make_trade(5), _make_trade(3), _make_trade(8)]
        stats = calculate_advanced_stats(trades)
        assert stats["win_count"] == 3
        assert stats["loss_count"] == 0
        assert stats["win_rate"] == 100.0
        assert stats["max_win"] == 8
        assert stats["max_loss"] == 3  # min(returns) = min(5,3,8)

    def test_all_losses(self):
        trades = [_make_trade(-2), _make_trade(-5), _make_trade(-1)]
        stats = calculate_advanced_stats(trades)
        assert stats["win_count"] == 0
        assert stats["loss_count"] == 3
        assert stats["win_rate"] == 0.0
        # sum(wins)=0, sum(losses)=-8, profit_factor=abs(0/-8)=0
        assert stats["profit_factor"] == 0.0

    def test_mixed_trades(self):
        trades = [_make_trade(5), _make_trade(-2), _make_trade(3), _make_trade(-1)]
        stats = calculate_advanced_stats(trades)
        assert stats["win_count"] == 2
        assert stats["loss_count"] == 2
        assert stats["total_return"] == 5
        assert stats["avg_return"] == 1.25

    def test_profit_factor(self):
        trades = [_make_trade(10), _make_trade(-5)]
        stats = calculate_advanced_stats(trades)
        assert stats["profit_factor"] == 2.0

    def test_zero_return_counted_as_loss(self):
        """return_pct=0 归为亏损（<=0）。"""
        trades = [_make_trade(0)]
        stats = calculate_advanced_stats(trades)
        assert stats["loss_count"] == 1

    def test_consecutive_wins(self):
        trades = [_make_trade(1), _make_trade(2), _make_trade(3), _make_trade(-1), _make_trade(4)]
        stats = calculate_advanced_stats(trades)
        assert stats["max_consecutive_wins"] == 3

    def test_consecutive_losses(self):
        trades = [_make_trade(-1), _make_trade(-2), _make_trade(1), _make_trade(-3), _make_trade(-4), _make_trade(-5)]
        stats = calculate_advanced_stats(trades)
        assert stats["max_consecutive_losses"] == 3

    def test_sharpe_ratio(self):
        """多笔交易有夏普比率。"""
        trades = [_make_trade(5), _make_trade(-2), _make_trade(3)]
        stats = calculate_advanced_stats(trades)
        assert "sharpe_ratio" in stats

    def test_max_drawdown(self):
        """累计收益回撤。"""
        trades = [_make_trade(10), _make_trade(-15), _make_trade(5)]
        stats = calculate_advanced_stats(trades)
        # 累计：10 -> -5 -> 0，peak=10, trough=-5, drawdown=15
        assert stats["max_drawdown"] == 15

    def test_all_fields_present(self):
        trades = [_make_trade(5), _make_trade(-2)]
        stats = calculate_advanced_stats(trades)
        expected_keys = {
            "total_trades", "win_count", "loss_count", "win_rate",
            "total_return", "avg_return", "avg_win", "avg_loss",
            "max_win", "max_loss", "profit_factor",
            "max_consecutive_wins", "max_consecutive_losses",
            "sharpe_ratio", "max_drawdown",
        }
        assert expected_keys.issubset(stats.keys())


# ═══════════════════════════════════════════════════════════════
# generate_ascii_chart
# ═══════════════════════════════════════════════════════════════


class TestGenerateAsciiChart:
    def test_empty_values(self):
        assert generate_ascii_chart([]) == ""

    def test_single_value(self):
        out = generate_ascii_chart([5])
        assert isinstance(out, str)
        assert len(out) > 0

    def test_with_title(self):
        out = generate_ascii_chart([1, 2, 3], title="测试标题")
        assert "测试标题" in out
        assert "===" in out

    def test_without_title(self):
        out = generate_ascii_chart([1, 2, 3])
        assert "测试标题" not in out

    def test_increasing_values(self):
        out = generate_ascii_chart([1, 2, 3, 4, 5])
        assert "█" in out

    def test_constant_values(self):
        """所有值相同 -> val_range=1，不除零。"""
        out = generate_ascii_chart([5, 5, 5])
        assert isinstance(out, str)

    def test_custom_dimensions(self):
        out = generate_ascii_chart([1, 2, 3], width=30, height=5)
        assert isinstance(out, str)


# ═══════════════════════════════════════════════════════════════
# generate_return_distribution
# ═══════════════════════════════════════════════════════════════


class TestGenerateReturnDistribution:
    def test_empty_returns(self):
        assert generate_return_distribution([]) == ""

    def test_single_return(self):
        out = generate_return_distribution([5])
        assert "收益分布" in out

    def test_multiple_returns(self):
        out = generate_return_distribution([1, 2, 3, 4, 5])
        assert "收益分布" in out
        assert "%" in out

    def test_constant_returns(self):
        """所有收益相同 -> bin_width=1，不除零。"""
        out = generate_return_distribution([5, 5, 5])
        assert isinstance(out, str)

    def test_custom_bins(self):
        out = generate_return_distribution([1, 2, 3, 4, 5, 6], bins=5)
        assert "收益分布" in out

    def test_negative_returns(self):
        out = generate_return_distribution([-5, -3, -1])
        assert "收益分布" in out


# ═══════════════════════════════════════════════════════════════
# generate_trade_timeline
# ═══════════════════════════════════════════════════════════════


class TestGenerateTradeTimeline:
    def test_empty_trades(self):
        assert generate_trade_timeline([]) == ""

    def test_single_trade(self):
        trades = [_make_trade(5)]
        out = generate_trade_timeline(trades)
        assert "交易时间线" in out
        assert "2024-01-01" in out
        assert "✓" in out  # 正收益

    def test_negative_trade_shows_x(self):
        trades = [_make_trade(-3)]
        out = generate_trade_timeline(trades)
        assert "✗" in out

    def test_max_trades_limit(self):
        """超过 max_trades 只显示最近 N 笔。"""
        trades = [_make_trade(i, signal=f"信号{i}") for i in range(1, 25)]
        out = generate_trade_timeline(trades, max_trades=5)
        # 最近 5 笔的信号应出现
        assert "信号24" in out
        assert "信号1" not in out  # 最早的被截断

    def test_signal_truncated(self):
        """信号字段截断到 20 字符。"""
        long_signal = "A" * 30
        trades = [_make_trade(5, signal=long_signal)]
        out = generate_trade_timeline(trades)
        # 截断后的信号应出现（20 字符）
        assert "A" * 20 in out


# ═══════════════════════════════════════════════════════════════
# generate_backtest_report
# ═══════════════════════════════════════════════════════════════


class TestGenerateBacktestReport:
    def test_no_trades_report(self):
        """无交易信号 -> 提示。"""
        with patch("strategies.patterns.backtest_report.backtest_strategy", return_value=[]):
            out = generate_backtest_report([], "测试股")
        assert "未产生交易信号" in out

    def test_full_report(self):
        trades = [_make_trade(5), _make_trade(-2), _make_trade(8)]
        with patch("strategies.patterns.backtest_report.backtest_strategy", return_value=trades):
            out = generate_backtest_report([{"day": "1", "close": 10, "volume": 100}], "测试股")
        assert "策略回测报告" in out
        assert "测试股" in out
        assert "核心指标" in out
        assert "风险指标" in out
        assert "总结" in out

    def test_high_win_rate_summary(self):
        """胜率>=60 -> 良好评语。"""
        trades = [_make_trade(5), _make_trade(3), _make_trade(8), _make_trade(-1)]
        with patch("strategies.patterns.backtest_report.backtest_strategy", return_value=trades):
            out = generate_backtest_report([{"day": "1", "close": 10, "volume": 100}], "测试股")
        assert "良好" in out

    def test_low_win_rate_summary(self):
        """胜率<50 -> 较差评语。"""
        trades = [_make_trade(5), _make_trade(-2), _make_trade(-8), _make_trade(-1)]
        with patch("strategies.patterns.backtest_report.backtest_strategy", return_value=trades):
            out = generate_backtest_report([{"day": "1", "close": 10, "volume": 100}], "测试股")
        assert "较差" in out

    def test_medium_win_rate_summary(self):
        """胜率 50-60 -> 一般评语。"""
        trades = [_make_trade(5), _make_trade(3), _make_trade(-2), _make_trade(-1)]
        with patch("strategies.patterns.backtest_report.backtest_strategy", return_value=trades):
            out = generate_backtest_report([{"day": "1", "close": 10, "volume": 100}], "测试股")
        assert "一般" in out

    def test_positive_avg_return(self):
        trades = [_make_trade(5), _make_trade(3)]
        with patch("strategies.patterns.backtest_report.backtest_strategy", return_value=trades):
            out = generate_backtest_report([{"day": "1", "close": 10, "volume": 100}], "测试股")
        assert "平均收益为正" in out

    def test_negative_avg_return(self):
        trades = [_make_trade(-5), _make_trade(-3)]
        with patch("strategies.patterns.backtest_report.backtest_strategy", return_value=trades):
            out = generate_backtest_report([{"day": "1", "close": 10, "volume": 100}], "测试股")
        assert "平均收益为负" in out

    def test_good_profit_factor(self):
        """盈亏比>1.5 -> 良好。"""
        trades = [_make_trade(15), _make_trade(-5)]  # PF=3
        with patch("strategies.patterns.backtest_report.backtest_strategy", return_value=trades):
            out = generate_backtest_report([{"day": "1", "close": 10, "volume": 100}], "测试股")
        assert "盈亏比良好" in out

    def test_low_profit_factor(self):
        """盈亏比<=1.5 -> 偏低。"""
        trades = [_make_trade(5), _make_trade(-4)]  # PF=1.25
        with patch("strategies.patterns.backtest_report.backtest_strategy", return_value=trades):
            out = generate_backtest_report([{"day": "1", "close": 10, "volume": 100}], "测试股")
        assert "盈亏比偏低" in out

    def test_custom_parameters_in_report(self):
        trades = [_make_trade(5)]
        with patch("strategies.patterns.backtest_report.backtest_strategy", return_value=trades):
            out = generate_backtest_report(
                [{"day": "1", "close": 10, "volume": 100}],
                "测试股",
                ma_short=5,
                ma_long=20,
                vol_threshold=3.0,
                hold_days=10,
                stop_loss=-8,
            )
        assert "MA5/MA20" in out
        assert "3.0x" in out
        assert "10" in out  # hold_days
        assert "-8%" in out

    def test_overfit_warning_present(self):
        """过拟合警示必须存在。"""
        trades = [_make_trade(5)]
        with patch("strategies.patterns.backtest_report.backtest_strategy", return_value=trades):
            out = generate_backtest_report([{"day": "1", "close": 10, "volume": 100}], "测试股")
        assert "外样本验证" in out
        assert "不构成实盘依据" in out


# ═══════════════════════════════════════════════════════════════
# generate_comparison_report
# ═══════════════════════════════════════════════════════════════


class TestGenerateComparisonReport:
    def test_single_stock(self):
        trades = [_make_trade(5), _make_trade(-2)]
        stocks_data = {"股票A": [{"day": "1", "close": 10, "volume": 100}]}
        with patch("strategies.patterns.backtest_report.backtest_strategy", return_value=trades):
            out = generate_comparison_report(stocks_data)
        assert "多股票策略对比报告" in out
        assert "股票A" in out
        assert "最佳表现" in out
        assert "最差表现" in out

    def test_multiple_stocks(self):
        trades_a = [_make_trade(10), _make_trade(5)]
        trades_b = [_make_trade(-3), _make_trade(-1)]
        stocks_data = {
            "股票A": [{"day": "1", "close": 10, "volume": 100}],
            "股票B": [{"day": "1", "close": 20, "volume": 200}],
        }
        with patch("strategies.patterns.backtest_report.backtest_strategy", side_effect=[trades_a, trades_b]):
            out = generate_comparison_report(stocks_data)
        assert "股票A" in out
        assert "股票B" in out
        assert "平均" in out
        # 最佳是 A，最差是 B
        assert "最佳表现" in out

    def test_overfit_warning_in_comparison(self):
        trades = [_make_trade(5)]
        stocks_data = {"股票A": [{"day": "1", "close": 10, "volume": 100}]}
        with patch("strategies.patterns.backtest_report.backtest_strategy", return_value=trades):
            out = generate_comparison_report(stocks_data)
        assert "外样本验证" in out

    def test_high_avg_win_rate_summary(self):
        """平均胜率>=60 -> 良好评语。"""
        trades = [_make_trade(10), _make_trade(8), _make_trade(-1)]  # 66.7%
        stocks_data = {"股票A": [{"day": "1", "close": 10, "volume": 100}]}
        with patch("strategies.patterns.backtest_report.backtest_strategy", return_value=trades):
            out = generate_comparison_report(stocks_data)
        assert "表现良好" in out

    def test_low_avg_win_rate_summary(self):
        """平均胜率<60 -> 一般评语。"""
        trades = [_make_trade(10), _make_trade(-5), _make_trade(-3)]  # 33%
        stocks_data = {"股票A": [{"day": "1", "close": 10, "volume": 100}]}
        with patch("strategies.patterns.backtest_report.backtest_strategy", return_value=trades):
            out = generate_comparison_report(stocks_data)
        assert "表现一般" in out

    def test_inf_profit_factor_handling(self):
        """全部盈利（PF=inf）-> finite_pfs 为空 -> avg_pf=inf。"""
        trades = [_make_trade(5), _make_trade(3)]  # 无亏损
        stocks_data = {
            "股票A": [{"day": "1", "close": 10, "volume": 100}],
            "股票B": [{"day": "1", "close": 20, "volume": 200}],
        }
        with patch("strategies.patterns.backtest_report.backtest_strategy", side_effect=[trades, trades]):
            out = generate_comparison_report(stocks_data)
        assert "多股票策略对比报告" in out


# ═══════════════════════════════════════════════════════════════
# load_kline_data
# ═══════════════════════════════════════════════════════════════


class TestLoadKlineData:
    def test_loads_json(self, tmp_path):
        import json

        path = tmp_path / "kline.json"
        path.write_text(json.dumps([{"day": "2024-01-01", "close": 10}]), encoding="utf-8")
        data = load_kline_data(str(path))
        assert data[0]["close"] == 10

    def test_file_not_found(self):
        import pytest

        with pytest.raises(FileNotFoundError):
            load_kline_data("/nonexistent/path/kline.json")
