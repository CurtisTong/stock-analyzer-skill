"""optimize_weights 跨窗口验证测试（2026-08-26 复盘 P2）。

60 日权重优化会过拟合历史（优化后 120/240 日全部失效）。
optimize_weights 现对 best_weights 做 60/120/240 三窗口验证，
三窗口均为正收益才标记 robust=True。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.cli import optimize_weights  # noqa: E402

STRATEGY = "balanced"  # registry 已注册的真实策略


def _report(total_return, sharpe, win_rate=55.0):
    return {
        "total_return_pct": total_return,
        "sharpe_ratio": sharpe,
        "win_rate_pct": win_rate,
    }


class TestCrossWindowValidation:
    def test_all_windows_positive_is_robust(self, monkeypatch):
        """全部窗口均为正收益 → robust=True。"""
        calls = []

        def fake_run_backtest(name, codes, top_n, days, rounds, weights=None):
            calls.append(days)
            # 网格搜索阶段（days=60, weights=None 的 baseline）返回负
            if weights is None and days == 60:
                return _report(-5.0, -0.5)
            # 网格搜索候选（weights 非 None）返回正
            if weights is not None:
                return _report(2.0, 0.3)
            # 跨窗口验证：60/120/240 全正
            return _report(1.0, 0.2)

        monkeypatch.setattr("backtest.cli.run_backtest", fake_run_backtest)
        result = optimize_weights(["sh600519"], STRATEGY, top_n=5, days=60)
        assert result["robust"] is True
        assert "cross_window_validation" in result
        assert set(result["cross_window_validation"].keys()) == {"60", "120", "240"}
        assert 120 in calls and 240 in calls

    def test_negative_window_not_robust(self, monkeypatch):
        """任一窗口负收益 → robust=False。"""

        def fake_run_backtest(name, codes, top_n, days, rounds, weights=None):
            if days == 240:
                return _report(-3.0, -0.2)  # 240 日窗口亏损（验证阶段）
            if weights is not None:
                return _report(2.0, 0.3)  # 网格候选
            return _report(1.0, 0.2)

        monkeypatch.setattr("backtest.cli.run_backtest", fake_run_backtest)
        result = optimize_weights(["sh600519"], STRATEGY, top_n=5, days=60)
        assert result["robust"] is False

    def test_validate_disabled_skips_cross_window(self, monkeypatch):
        """validate=False 时不跑跨窗口验证。"""
        calls = []

        def fake_run_backtest(name, codes, top_n, days, rounds, weights=None):
            calls.append(days)
            return _report(1.0, 0.2)

        monkeypatch.setattr("backtest.cli.run_backtest", fake_run_backtest)
        result = optimize_weights(
            ["sh600519"], STRATEGY, top_n=5, days=60, validate=False
        )
        assert "cross_window_validation" not in result
        assert "robust" not in result
        assert 120 not in calls and 240 not in calls


class TestOptimizeFullFactorSet:
    """optimize_weights 全因子网格（原只取 4 键，34% 权重被置零）。"""

    def test_weights_include_all_factors(self, monkeypatch):
        """传给 run_backtest 的候选权重应含全部 7 因子（含 volatility/chip/dividend）。"""
        seen = []

        def fake_run_backtest(name, codes, top_n, days, rounds, weights=None):
            if weights is not None:
                seen.append(weights)
            return _report(1.0, 0.2)

        monkeypatch.setattr("backtest.cli.run_backtest", fake_run_backtest)
        optimize_weights(["sh600519"], STRATEGY, top_n=5, days=60, validate=False)
        assert seen, "应产生候选权重"
        all_keys = set().union(*(w.keys() for w in seen))
        for k in (
            "quality",
            "valuation",
            "momentum",
            "liquidity",
            "volatility",
            "chip",
            "dividend",
        ):
            assert k in all_keys, f"候选权重缺少因子 {k}"
        # 每个候选权重归一化（和 ≈ 1）
        for w in seen:
            assert abs(sum(w.values()) - 1.0) < 0.01
