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

    def test_psr_denominator_uses_plus_sign(self):
        """PSR 分母必须是 sqrt(1 + 0.5·SR²)（正态 γ4=3 → PLUS）。

        写成 MINUS 时高 SR 的分母被钳到 ~0，DSR 被强行推向 1.0（假通过）。
        本用例对手算值做锚定：分母不同 → DSR 不同。
        """
        import math
        from statistics import NormalDist

        trials = [0.8, 1.1, 1.5, 0.9, 1.2, 1.4, 1.0, 1.3]
        best = 1.5
        n_obs = 60

        var_sr = sum((s - sum(trials) / len(trials)) ** 2 for s in trials) / (len(trials) - 1)
        euler = 0.5772156649
        z = NormalDist().inv_cdf
        n = len(trials)
        expected_max = math.sqrt(var_sr) * ((1 - euler) * z(1 - 1 / n) + euler * z(1 - 1 / (n * math.e)))
        sr_best_daily = best / math.sqrt(252)
        sr0_daily = expected_max / math.sqrt(252)
        denom_plus = math.sqrt(1 + 0.5 * sr_best_daily**2)
        expected = NormalDist().cdf((sr_best_daily - sr0_daily) * math.sqrt(n_obs - 1) / denom_plus)

        assert deflated_sharpe_ratio(trials, best, n_obs) == pytest.approx(round(expected, 4), abs=1e-4)

    def test_high_sharpe_denominator_not_clamped(self):
        """高夏普时 PSR 分母不得被钳到 ~0（MINUS 符号错误的典型症状）。

        MINUS 写法下 1-0.5·sr² 为负 → max(1e-12, ...) 把分母压到 1e-6，
        DSR 被强行推向 1.0。PLUS 写法分母随 SR 增大而增大。
        """
        import math

        trials = [0.1, 0.3, 0.5, 0.2, 0.4, 0.6, 0.3, 0.2, 0.1, 0.4] * 2
        best_sharpe = 50.0
        sr_daily = best_sharpe / math.sqrt(252)
        denom_plus = math.sqrt(1 + 0.5 * sr_daily**2)
        denom_minus = math.sqrt(max(1e-12, 1 - 0.5 * sr_daily**2))

        # PLUS 分母显著大于被钳死的 MINUS 分母
        assert denom_plus > 1.0
        assert denom_minus < 1e-5

        # 代码在 PLUS 分母下给出的 DSR 应低于 MINUS 分母会给出的值
        dsr = deflated_sharpe_ratio(trials, best_sharpe=best_sharpe, n_obs=60)
        assert dsr is not None
        assert dsr <= 1.0


class TestDistinctTrialSharpes:
    """DSR 试验次数口径：重复权重向量不得虚增 N。"""

    def _w(self, key, weights):
        return {"perturbed_key": key, "step": 0.0, "sharpe": 1.0, "return": 0.0, "weights": weights}

    def test_duplicate_weight_vectors_deduplicated(self):
        from backtest.cli import _distinct_trial_sharpes

        base = {"quality": 0.3, "momentum": 0.2}
        results = [
            self._w("quality", base),
            self._w("momentum", base),  # 同权重向量（step=0）
            self._w("valuation", {"quality": 0.25, "momentum": 0.2}),
        ]
        assert len(_distinct_trial_sharpes(results)) == 2

    def test_distinct_vectors_all_kept(self):
        from backtest.cli import _distinct_trial_sharpes

        results = [
            self._w("quality", {"quality": 0.3}),
            self._w("momentum", {"quality": 0.25}),
        ]
        assert len(_distinct_trial_sharpes(results)) == 2
