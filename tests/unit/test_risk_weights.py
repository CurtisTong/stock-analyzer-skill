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
        assert w == {
            "A": pytest.approx(33.33, abs=0.01),
            "B": pytest.approx(33.33, abs=0.01),
            "C": pytest.approx(33.33, abs=0.01),
        }

    def test_cap_applied(self):
        w = inverse_volatility_weights({"A": 0.5, "B": 2.0, "C": 2.0}, cap_pct=50.0)
        assert w["A"] <= 50.0  # 被钳制
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
