"""
walk-forward 窗口边界测试（P0-1 修复）。

修复前：窗口边界（train_start/train_end/test_start/test_end）从未传给回测引擎，
IS/OOS 两次调用仅 total_days 不同，OOS 数据被 IS 见过，所有窗口产出相同结果。
修复后：SimContext 增加 eval_start/eval_end，OOS 评估区间在 IS 之后。
"""

import pytest

from data.types import KlineBar


def _make_finance_obj(**kwargs):
    """构造 FinanceRecord dataclass。"""
    from data.types import FinanceRecord

    defaults = dict(
        eps=50.0,
        roe=30.5,
        revenue_yoy=15.2,
        net_profit_yoy=18.3,
        gross_margin=91.5,
        debt_ratio=18.7,
        ocf_per_share=55.0,
    )
    defaults.update(kwargs)
    return FinanceRecord(**defaults)


class TestWalkForwardWindows:
    """P0-1: 窗口边界真实生效。"""

    def _mock_all(self, monkeypatch):
        """mock 数据层：前段上涨 + 后段下跌的合成 K 线（不同窗口收益不同）。"""
        import backtest
        from datetime import datetime, timedelta

        finance_obj = _make_finance_obj()
        monkeypatch.setattr(
            backtest.engine, "get_finance", lambda code: ([finance_obj], None)
        )
        today = datetime.now()

        def _mock_kline(code, scale=240, datalen=300):
            n = max(datalen, 300)
            bars = []
            for i in range(n):
                d = today - timedelta(days=n - i)
                if i < 150:
                    price = 10 + i * 0.3  # 前段上涨
                else:
                    price = 55 - (i - 150) * 0.3  # 后段下跌
                bars.append(
                    KlineBar(
                        day=d.strftime("%Y-%m-%d"),
                        close=price,
                        open=price,
                        high=price,
                        low=price,
                    )
                )
            return bars

        monkeypatch.setattr(backtest.engine, "get_kline", _mock_kline)

    def test_oos_evaluates_after_train(self, monkeypatch):
        """OOS 轮次日期应晚于 IS 轮次日期（样本外语义）。"""
        from backtest.walk_forward import run_walk_forward, WalkForwardConfig

        self._mock_all(monkeypatch)
        cfg = WalkForwardConfig(
            strategy_name="balanced",
            codes=["sh600519"],
            top_n=1,
            holding_days=10,
            train_days=120,
            test_days=60,
            n_windows=1,
        )
        result = run_walk_forward(cfg)
        assert result.n_valid_windows >= 1
        win = result.windows[0]
        assert win["status"] == "ok"
        # IS 与 OOS 收益序列都应非空且不同（修复前两者相同）
        is_returns = win["is_returns"]
        oos_returns = win["oos_returns"]
        assert is_returns, "IS 段应产出轮次"
        assert oos_returns, "OOS 段应产出轮次"
        assert is_returns != oos_returns, "修复前 IS/OOS 重复；修复后窗口边界应生效"

    def test_distinct_windows_distinct_results(self, monkeypatch):
        """不同窗口的 OOS 收益应不同（修复前所有窗口产出相同结果）。"""
        from backtest.walk_forward import run_walk_forward, WalkForwardConfig

        self._mock_all(monkeypatch)
        cfg = WalkForwardConfig(
            strategy_name="balanced",
            codes=["sh600519"],
            top_n=1,
            holding_days=10,
            train_days=120,
            test_days=60,
            n_windows=2,
        )
        result = run_walk_forward(cfg)
        oos_by_window = [
            tuple(w["oos_returns"]) for w in result.windows if w["status"] == "ok"
        ]
        assert len(oos_by_window) >= 2
        # 修复前所有窗口相同（无窗口边界）；修复后窗口 1 的 OOS 在窗口 0 之后
        assert oos_by_window[0] != oos_by_window[1], "不同窗口应产出不同 OOS 结果"

    def test_default_behavior_unchanged(self, monkeypatch):
        """eval_start=0/eval_end=None 时 simulate_strategy 行为不变（回归）。"""
        import backtest

        self._mock_all(monkeypatch)
        ctx = backtest.SimContext(
            strategy_name="balanced", codes=["sh600519"], top_n=1, holding_days=10
        )
        result = backtest.simulate_strategy(ctx)
        assert "error" not in result
        assert result["total_periods"] > 1
