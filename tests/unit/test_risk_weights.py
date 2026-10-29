"""逆波动率加权测试（v1.24.0）。"""

from __future__ import annotations

import pytest

from portfolio.risk_weights import inverse_volatility_weights, daily_volatility_from_closes


class TestInverseVolatilityWeights:
    def test_low_vol_gets_more_weight(self):
        w = inverse_volatility_weights({"A": 1.0, "B": 3.0})
        assert w["A"] > w["B"]
        assert round(sum(w.values()), 2) == 100.0

    def test_equal_vol_equal_weight(self):
        w = inverse_volatility_weights({"A": 2.0, "B": 2.0, "C": 2.0})
        for k in ("A", "B", "C"):
            assert w[k] == pytest.approx(33.33, abs=0.02)
        assert round(sum(w.values()), 2) == 100.0

    def test_cap_applied(self):
        w = inverse_volatility_weights({"A": 0.5, "B": 2.0, "C": 2.0}, cap_pct=50.0)
        assert w["A"] <= 50.0  # 被钳制
        assert round(sum(w.values()), 2) == 100.0

    def test_cap_respected_by_all_assets(self):
        """钳制后回分的资产自身也不得突破 cap（一次性回分不收敛的回归锚点）。

        修复前：低波 0.8 / 高波 4.0，cap=40 → 高波回分到 60%，仍超上限。
        3 只资产、cap=40 → cap×n=120 ≥ 100，约束可行，权重和仍为 100。
        """
        w = inverse_volatility_weights(
            {"sh601398": 0.80, "sz300xxx": 4.00, "sh600519": 1.0},
            cap_pct=40.0,
        )
        assert all(v <= 40.0 + 1e-6 for v in w.values()), w
        assert round(sum(w.values()), 2) == 100.0

    def test_infeasible_cap_leaves_cash_not_breach(self):
        """cap×n < 100 时不得为凑满 100 而突破上限（剩余视为现金）。"""
        w = inverse_volatility_weights({"A": 0.1, "B": 0.10001}, cap_pct=40.0)
        assert all(v <= 40.0 + 1e-6 for v in w.values()), w
        assert sum(w.values()) <= 80.0 + 1e-6

    def test_weight_sum_always_100(self):
        """逐项舍入不得让权重和漂移（修复前 37.7% 的随机用例 ≠ 100）。"""
        import random

        rng = random.Random(20261029)
        for _ in range(200):
            n = rng.randint(2, 8)
            vols = {f"S{i}": rng.uniform(0.05, 5.0) for i in range(n)}
            w = inverse_volatility_weights(vols)
            assert round(sum(w.values()), 2) == 100.0

    def test_zero_vol_stock_excluded(self):
        w = inverse_volatility_weights({"A": 1.0, "B": 0.0})
        assert w == {"A": 100.0}

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            inverse_volatility_weights({})

    def test_all_zero_raises(self):
        with pytest.raises(ValueError):
            inverse_volatility_weights({"A": 0.0, "B": 0.0})


class TestDailyVolatility:
    def test_computes_from_closes(self):
        closes = [10.0, 11.0, 10.5, 11.5, 11.0]
        v = daily_volatility_from_closes(closes)
        assert v is not None
        assert v > 0

    def test_flat_series_returns_none(self):
        assert daily_volatility_from_closes([10.0, 10.0, 10.0]) is None

    def test_too_short_returns_none(self):
        assert daily_volatility_from_closes([10.0, 11.0]) is None

    def test_zero_price_scaled(self):
        closes = [10.0, 0.0, 11.0, 10.0]
        assert daily_volatility_from_closes(closes) is not None
