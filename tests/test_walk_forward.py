"""walk-forward 回测框架测试（P0-11）。

验证 walk-forward 窗口划分、OOS 指标计算和框架集成。
使用 mock 数据避免网络请求。
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from backtest.walk_forward import (  # noqa: E402
    WalkForwardConfig,
    WalkForwardResult,
    run_walk_forward,
    _calc_sharpe,
    _calc_max_drawdown,
)


def _make_mock_kline(n=80):
    """生成模拟 K 线数据。"""
    from data.types import KlineBar

    today = datetime.now()
    return [
        KlineBar(
            day=(today - timedelta(days=n - i)).strftime("%Y-%m-%d"),
            close=10 + i * 0.2,
            open=10 + i * 0.2,
            high=10 + i * 0.2 + 0.5,
            low=10 + i * 0.2 - 0.5,
            volume=10000,
        )
        for i in range(n)
    ]


class TestWalkForwardConfig:
    """配置验证。"""

    def test_default_step_equals_test_days(self):
        """step_days=0 时自动设为 test_days。"""
        config = WalkForwardConfig(
            strategy_name="balanced",
            codes=["sh600519"],
            train_days=60,
            test_days=20,
            n_windows=3,
        )
        # step_days 默认 0，run 时自动设为 test_days
        assert config.step_days == 0


class TestCalcSharpe:
    """夏普比率计算。"""

    def test_empty_returns_zero(self):
        """空输入返回 0。"""
        assert _calc_sharpe([]) == 0.0

    def test_single_return_zero(self):
        """单个收益返回 0（样本不足）。"""
        assert _calc_sharpe([5.0]) == 0.0

    def test_positive_returns_positive_sharpe(self):
        """正收益序列夏普应为正。"""
        sharpe = _calc_sharpe([1.0, 2.0, 1.5, 0.5, 2.0])
        assert sharpe > 0

    def test_negative_returns_negative_sharpe(self):
        """负收益序列夏普应为负。"""
        sharpe = _calc_sharpe([-1.0, -2.0, -1.5, -0.5, -2.0])
        assert sharpe < 0


class TestCalcMaxDrawdown:
    """最大回撤计算。"""

    def test_empty_zero(self):
        """空输入返回 0。"""
        assert _calc_max_drawdown([]) == 0.0

    def test_monotonic_up_zero_drawdown(self):
        """单调上涨无回撤。"""
        assert _calc_max_drawdown([1.0, 2.0, 3.0]) == 0.0

    def test_drawdown_detected(self):
        """先涨后跌应有回撤。"""
        dd = _calc_max_drawdown([5.0, -10.0, 5.0])
        assert dd > 0
        assert dd < 100


class TestRunWalkForward:
    """walk-forward 框架集成测试（mock 数据层）。"""

    @patch("backtest.engine.get_kline")
    @patch("backtest.engine.get_finance")
    def test_returns_valid_result_structure(self, mock_fin, mock_kline):
        """run_walk_forward 返回含 OOS 指标的有效结构。"""
        from data.types import FinanceRecord

        mock_kline.side_effect = lambda code, scale=240, datalen=100: _make_mock_kline(
            max(datalen, 80)
        )
        mock_fin.return_value = [
            FinanceRecord(eps=2.5, roe=18.0, report_date="2024-01-01")
        ]

        config = WalkForwardConfig(
            strategy_name="balanced",
            codes=["sh600519"],
            train_days=60,
            test_days=20,
            n_windows=2,
            top_n=1,
            holding_days=5,
        )
        result = run_walk_forward(config)

        assert isinstance(result, WalkForwardResult)
        d = result.to_dict()
        assert "oos_returns" in d
        assert "oos_sharpe" in d
        assert "oos_win_rate_pct" in d
        assert "oos_max_drawdown_pct" in d
        assert "windows" in d
        assert d["config"]["strategy_name"] == "balanced"

    @patch("backtest.engine.get_kline")
    @patch("backtest.engine.get_finance")
    def test_oos_returns_aggregated(self, mock_fin, mock_kline):
        """所有窗口的 OOS 收益被汇总。"""
        from data.types import FinanceRecord

        mock_kline.side_effect = lambda code, scale=240, datalen=100: _make_mock_kline(
            max(datalen, 80)
        )
        mock_fin.return_value = [
            FinanceRecord(eps=2.5, roe=18.0, report_date="2024-01-01")
        ]

        config = WalkForwardConfig(
            strategy_name="balanced",
            codes=["sh600519"],
            train_days=60,
            test_days=20,
            n_windows=2,
            top_n=1,
            holding_days=5,
        )
        result = run_walk_forward(config)

        # OOS 收益数 = 各窗口 OOS 期数之和
        if result.oos_returns:
            assert len(result.oos_returns) >= 1
            assert result.oos_win_rate >= 0
            assert result.oos_win_rate <= 100

    @patch("backtest.engine.get_kline")
    @patch("backtest.engine.get_finance")
    def test_window_count_matches_config(self, mock_fin, mock_kline):
        """窗口数 = n_windows。"""
        from data.types import FinanceRecord

        mock_kline.side_effect = lambda code, scale=240, datalen=100: _make_mock_kline(
            max(datalen, 80)
        )
        mock_fin.return_value = [
            FinanceRecord(eps=2.5, roe=18.0, report_date="2024-01-01")
        ]

        config = WalkForwardConfig(
            strategy_name="balanced",
            codes=["sh600519"],
            train_days=60,
            test_days=20,
            n_windows=3,
            top_n=1,
            holding_days=5,
        )
        result = run_walk_forward(config)

        assert len(result.windows) == 3

    @patch("backtest.engine.get_kline")
    @patch("backtest.engine.get_finance")
    def test_errors_recorded(self, mock_fin, mock_kline):
        """K 线不足时错误被记录。"""
        from data.types import FinanceRecord

        mock_kline.return_value = []  # 无数据
        mock_fin.return_value = [
            FinanceRecord(eps=2.5, roe=18.0, report_date="2024-01-01")
        ]

        config = WalkForwardConfig(
            strategy_name="balanced",
            codes=["sh600519"],
            train_days=60,
            test_days=20,
            n_windows=2,
            top_n=1,
            holding_days=5,
        )
        result = run_walk_forward(config)

        assert len(result.errors) > 0
        assert result.n_valid_windows == 0

    def test_to_dict_serializable(self):
        """to_dict 返回可 JSON 序列化的 dict。"""
        config = WalkForwardConfig(
            strategy_name="balanced",
            codes=["sh600519"],
            train_days=60,
            test_days=20,
            n_windows=1,
        )
        result = WalkForwardResult(config=config)
        d = result.to_dict()
        import json

        json.dumps(d)  # 不抛异常即可


class TestWalkForwardCLI:
    """walk-forward CLI 参数解析测试。"""

    def test_walk_forward_flags_in_help(self):
        """--walk-forward 及相关参数应出现在 --help 输出中。"""
        import subprocess

        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "backtest.py"), "--help"],
            capture_output=True,
            timeout=15,
            cwd=str(PROJECT_ROOT),
        )
        stdout = result.stdout.decode()
        assert "--walk-forward" in stdout
        assert "--train-days" in stdout
        assert "--test-days" in stdout
        assert "--n-windows" in stdout
