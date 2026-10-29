"""寻优过拟合诊断测试（v1.24.0）：敏感性平台 + deflated Sharpe。"""

from __future__ import annotations

import pytest

from backtest.cli import (
    SENSITIVITY_OUTLIER_THRESHOLD,
    SENSITIVITY_SPIKE_THRESHOLD,
    _overfit_warnings,
    _sensitivity_by_key,
)
from backtest.metrics import deflated_sharpe_ratio


def _row(key, step, sharpe):
    return {"perturbed_key": key, "step": step, "sharpe": sharpe, "return": 5.0}


class TestSensitivityByKey:
    def test_groups_by_perturbed_key(self):
        results = [
            _row("quality", -0.05, 0.8),
            _row("quality", 0.0, 1.0),
            _row("quality", 0.05, 0.9),
            _row("momentum", -0.05, 0.5),
            _row("momentum", 0.0, 0.6),
            _row("momentum", 0.05, 0.7),
        ]
        sens = _sensitivity_by_key(results, ["quality", "momentum"])
        assert sens["quality"]["sharpes"] == [0.8, 1.0, 0.9]
        assert sens["quality"]["steps"] == [-0.05, 0.0, 0.05]
        assert sens["momentum"]["sharpes"] == [0.5, 0.6, 0.7]


class TestOverfitWarnings:
    def test_spike_detected(self):
        # quality 在 +0.05 档出现尖峰（比基准档高 0.8 > 阈值 0.5）
        results = [
            _row("quality", -0.05, 0.8),
            _row("quality", 0.0, 1.0),
            _row("quality", 0.05, 1.8),
            _row("momentum", -0.05, 0.5),
            _row("momentum", 0.0, 0.6),
            _row("momentum", 0.05, 0.7),
        ]
        warnings = _overfit_warnings(results, best_score=1.8, base_score=0.6)
        assert any("尖峰" in w and "quality" in w for w in warnings)

    def test_plateau_no_warning(self):
        results = [
            _row("quality", -0.05, 0.95),
            _row("quality", 0.0, 1.0),
            _row("quality", 0.05, 1.05),
            _row("momentum", -0.05, 0.55),
            _row("momentum", 0.0, 0.6),
            _row("momentum", 0.05, 0.65),
        ]
        assert _overfit_warnings(results, best_score=1.05, base_score=0.6) == []

    def test_outlier_warning(self):
        results = [_row("quality", s, 0.5) for s in (-0.05, 0.0, 0.05)]
        results += [_row("momentum", s, 0.6) for s in (-0.05, 0.0, 0.05)]
        best = 0.5 + SENSITIVITY_OUTLIER_THRESHOLD + 0.5
        warnings = _overfit_warnings(results, best_score=best, base_score=0.3)
        assert any("离群" in w for w in warnings)


class TestDeflatedSharpe:
    def test_insufficient_trials_returns_none(self):
        assert deflated_sharpe_ratio([0.5], 0.5, 60) is None
        assert deflated_sharpe_ratio([0.5, 0.4], 0.5, 10) is None  # n_obs < 30

    def test_zero_dispersion_returns_none(self):
        assert deflated_sharpe_ratio([0.5] * 10, 0.5, 60) is None

    def test_spiky_best_is_not_significant_on_short_window(self):
        """短窗口 + 尖峰最优 → DSR 低（选择偏差主导）。"""
        trials = [0.1, 0.3, 0.5, 0.2, 0.4, 0.6, 0.3, 0.2, 0.1, 0.4] * 2
        dsr = deflated_sharpe_ratio(trials, best_sharpe=1.5, n_obs=60)
        assert dsr is not None
        assert dsr < 0.95

    def test_longer_window_raises_dsr(self):
        """同样的试验分布，窗口翻 4 倍 DSR 显著上升。"""
        trials = [0.1, 0.3, 0.5, 0.2, 0.4, 0.6, 0.3, 0.2, 0.1, 0.4] * 2
        short = deflated_sharpe_ratio(trials, best_sharpe=1.5, n_obs=60)
        long = deflated_sharpe_ratio(trials, best_sharpe=1.5, n_obs=240)
        assert long > short

    def test_dsr_in_unit_interval(self):
        trials = [0.1, 0.3, 0.5, 0.2, 0.4, 0.6, 0.3, 0.2, 0.1, 0.4] * 2
        for n_obs in (30, 60, 120, 240):
            dsr = deflated_sharpe_ratio(trials, best_sharpe=1.5, n_obs=n_obs)
            assert 0.0 <= dsr <= 1.0
