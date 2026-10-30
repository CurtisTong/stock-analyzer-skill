"""市场级情绪 overlay 第 5 层测试（v1.26 阶段 3）。

分工：个股级情绪 → 因子（横截面区分度）；市场级情绪 → overlay 权重调节（连续量，
补 regime 6 态判定的粗粒度不足）。
"""

from __future__ import annotations

import pytest


def _snapshot(limit_up=47, broken=31, max_height=5, sectors=None):
    return {
        "date": "20261030",
        "limit_up_count": limit_up,
        "broken_count": broken,
        "max_height": max_height,
        "height_distribution": {"1": limit_up},
        "sectors": sectors
        or {
            "专用设备": {"limit_up": 2, "broken": 0, "count": 2},
            "汽车零部": {"limit_up": 1, "broken": 0, "count": 1},
        },
    }


class TestMarketMetrics:
    def test_seal_rate(self):
        """封板率 = 涨停 / (涨停 + 炸板)。"""
        from strategies.regime.sentiment_overlay import market_sentiment_metrics

        m = market_sentiment_metrics(_snapshot(47, 31))
        assert m["seal_rate"] == pytest.approx(47 / 78, abs=1e-4)

    def test_sector_concentration_top3(self):
        """板块集中度 = top3 板块涨停家数 / 全部涨停家数。"""
        from strategies.regime.sentiment_overlay import market_sentiment_metrics

        m = market_sentiment_metrics(_snapshot(3, 0))
        assert m["sector_concentration"] == pytest.approx(1.0)

    def test_empty_snapshot_returns_none_fields(self):
        from strategies.regime.sentiment_overlay import market_sentiment_metrics

        m = market_sentiment_metrics(None)
        assert m["seal_rate"] is None
        assert m["sector_concentration"] is None

    def test_zero_pools_no_division_error(self):
        from strategies.regime.sentiment_overlay import market_sentiment_metrics

        m = market_sentiment_metrics(_snapshot(0, 0))
        assert m["seal_rate"] is None


class TestSentimentState:
    def test_ice_when_seal_rate_low(self):
        """封板率低 → 冰点。"""
        from strategies.regime.sentiment_overlay import market_sentiment_metrics, sentiment_state

        m = market_sentiment_metrics(_snapshot(20, 60))  # 封板率 0.25
        assert sentiment_state(m) == "ice"

    def test_ice_when_promotion_low(self):
        """晋级率低 → 冰点（历史充足时）。"""
        from strategies.regime.sentiment_overlay import market_sentiment_metrics, sentiment_state

        m = market_sentiment_metrics(_snapshot(47, 31), promotion_rate=0.10)
        assert sentiment_state(m) == "ice"

    def test_hot_requires_all_conditions(self):
        """亢奋需同时满足：封板率高 + 连板高度高 + 资金拥挤。"""
        from strategies.regime.sentiment_overlay import market_sentiment_metrics, sentiment_state

        # 封板率高但高度不够 → 非亢奋
        m = market_sentiment_metrics(_snapshot(90, 10, max_height=3))
        assert sentiment_state(m) != "hot"

        # 高度够但封板率不够 → 非亢奋
        m = market_sentiment_metrics(_snapshot(40, 40, max_height=8))
        assert sentiment_state(m) != "hot"

        # 三个条件都满足 → 亢奋
        m = market_sentiment_metrics(_snapshot(90, 10, max_height=7))
        assert sentiment_state(m) == "hot"

    def test_normal(self):
        from strategies.regime.sentiment_overlay import market_sentiment_metrics, sentiment_state

        m = market_sentiment_metrics(_snapshot(47, 31, max_height=5))
        assert sentiment_state(m) == "normal"


class TestOverlayMultipliers:
    def test_ice_pressures_momentum(self):
        """冰点：压制 momentum，提升 quality/valuation。"""
        from strategies.regime.sentiment_overlay import market_sentiment_metrics, sentiment_overlay_multipliers

        m = market_sentiment_metrics(_snapshot(20, 60))
        mults = sentiment_overlay_multipliers(m)
        assert mults["momentum"] < 1.0
        assert mults["quality"] > 1.0
        assert mults["valuation"] > 1.0

    def test_normal_no_adjustment(self):
        from strategies.regime.sentiment_overlay import market_sentiment_metrics, sentiment_overlay_multipliers

        m = market_sentiment_metrics(_snapshot(47, 31))
        assert sentiment_overlay_multipliers(m) == {}


class TestOverlayFifthLayer:
    """overlay 的第 5 层接入验证。"""

    def _weights(self):
        return {"quality": 0.3, "valuation": 0.2, "momentum": 0.2, "liquidity": 0.1, "volatility": 0.1}

    def test_layer_applied(self):
        """传入 sentiment_multipliers → momentum 被压制。"""
        from strategies.regime.classifier import RegimeState
        from strategies.regime.overlay import compute_overlay_weights

        base = compute_overlay_weights(self._weights(), RegimeState.RANGE)
        adjusted = compute_overlay_weights(self._weights(), RegimeState.RANGE, sentiment_multipliers={"momentum": 0.5})
        assert adjusted["momentum"] < base["momentum"]

    def test_layer_absent_is_noop(self):
        """不传 → 与历史行为完全一致（默认不启用）。"""
        from strategies.regime.classifier import RegimeState
        from strategies.regime.overlay import compute_overlay_weights

        base = compute_overlay_weights(self._weights(), RegimeState.RANGE)
        same = compute_overlay_weights(self._weights(), RegimeState.RANGE, sentiment_multipliers=None)
        assert base == same

    def test_weights_sum_to_one(self):
        """叠加后权重和仍为 1.0。"""
        from strategies.regime.classifier import RegimeState
        from strategies.regime.overlay import compute_overlay_weights

        w = compute_overlay_weights(
            self._weights(),
            RegimeState.RANGE,
            sentiment_multipliers={"momentum": 0.5, "quality": 1.2},
        )
        assert sum(w.values()) == pytest.approx(1.0, abs=1e-3)

    def test_layer_order_after_ic(self):
        """情绪层在 IC 层之后叠加（最细粒度最后生效）。"""
        from strategies.regime.classifier import RegimeState
        from strategies.regime.overlay import compute_overlay_weights

        w = compute_overlay_weights(
            self._weights(),
            RegimeState.RANGE,
            ic_multipliers={"momentum": 0.5},
            sentiment_multipliers={"momentum": 0.8},
        )
        # IC 层 0.5 与情绪层 0.8 是乘法叠加（非覆盖）
        only_ic = compute_overlay_weights(self._weights(), RegimeState.RANGE, ic_multipliers={"momentum": 0.5})
        assert w["momentum"] < only_ic["momentum"]
