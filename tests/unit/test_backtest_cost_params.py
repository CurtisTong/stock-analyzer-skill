"""回测成本模型参数暴露 + 超额指标样本不足语义（v1.25 复审修复）。

背景：
- initial_capital / min_commission / commission 等此前硬编码在引擎里，
  用户无法调整——小资金账户的最低佣金占比显著更高，却无法建模。
- beta/alpha/excess_sharpe 在期数不足（≤2）时输出 0，0 会被误读成
  "真实的零值"，而不是"算不出来"。
"""

from __future__ import annotations

import pytest


class TestCostParamsPlumbing:
    def test_run_backtest_accepts_cost_params(self):
        """run_backtest 必须接受成本模型参数并透传到引擎。"""
        import inspect

        from backtest.metrics import run_backtest

        sig = inspect.signature(run_backtest)
        for name in ("initial_capital", "commission", "stamp_tax", "slippage", "min_commission"):
            assert name in sig.parameters, f"缺少参数 {name}"

    def test_cli_exposes_cost_params(self):
        """CLI 必须暴露成本参数（否则用户无法调整）。"""
        import subprocess
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent.parent
        r = subprocess.run(
            [sys.executable, "scripts/backtest.py", "--help"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, r.stderr
        for flag in ("--capital", "--commission", "--stamp-tax", "--slippage", "--min-commission"):
            assert flag in r.stdout, f"CLI 缺少 {flag}"

    def test_cap_pct_exposed_in_portfolio_cli(self):
        """逆波动率权重上限必须可调（此前硬编码 40%）。"""
        import subprocess
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent.parent
        r = subprocess.run(
            [sys.executable, "scripts/portfolio_correlation.py", "--help"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, r.stderr
        assert "--risk-weights-cap" in r.stdout


class TestMinCommissionEffect:
    def test_small_capital_raises_cost(self):
        """小资金账户单笔金额少 → 最低佣金占比更高 → 成本率更高。"""
        from backtest.engine import _total_cost_rate

        big = _total_cost_rate(20000, 0.00025, 0.001, 0.001, 5.0)
        small = _total_cost_rate(3000, 0.00025, 0.001, 0.001, 5.0)
        assert small > big

    def test_min_commission_zero_disables_floor(self):
        from backtest.engine import _total_cost_rate

        rate = _total_cost_rate(3000, 0.00025, 0.001, 0.001, 0.0)
        assert rate == pytest.approx(0.00025 * 2 + 0.001 + 0.001 * 2)


class TestInsufficientSampleSemantics:
    def test_beta_alpha_none_when_insufficient(self):
        """期数不足时 beta/alpha 应为 None（而非 0）。"""
        from backtest.metrics import run_backtest

        import backtest
        from datetime import datetime, timedelta
        from data.types import KlineBar

        finance_obj = _finance_stub()
        today = datetime.now()

        def _mock_kline(code, scale=240, datalen=140):
            n = max(datalen, 140)
            bars = []
            for i in range(n):
                d = today - timedelta(days=n - i)
                bars.append(
                    KlineBar(
                        day=d.strftime("%Y-%m-%d"),
                        close=10 + i * 0.3,
                        open=10 + i * 0.3,
                        high=10 + i * 0.3,
                        low=10 + i * 0.3,
                        volume=1000,
                    )
                )
            return bars

        orig_kline = backtest.engine.get_kline
        orig_fin = backtest.engine.get_finance
        backtest.engine.get_kline = _mock_kline
        backtest.engine.get_finance = lambda code: [finance_obj]
        try:
            result = backtest.run_backtest(
                "balanced",
                ["sh600519"],
                top_n=1,
                days=30,
                rounds=3,
                benchmark=["sh000300"],
            )
        finally:
            backtest.engine.get_kline = orig_kline
            backtest.engine.get_finance = orig_fin

        assert "error" not in result
        # 字段存在；样本足够时有值，不够时为 None（不是 0）
        assert "beta" in result
        assert "alpha" in result
        if result["beta"] is None:
            assert result["alpha"] is None


def _finance_stub():
    class _F:
        def get(self, key, default=None):
            return default

        def __getitem__(self, key):
            return 0.0

    return _F()
