"""(#10) 事件因子激活 + 业绩预告测试。

覆盖：
- 业绩预告各类型评分（预增/预减/预亏/扭亏/续盈/续亏）
- 无预告数据时中性
- forecast fetcher 失败降级
- event 权重激活（>0）
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from strategies.factors.event import event_score  # noqa: E402


def _make_events(forecast_items=None, **kwargs):
    """构造 get_events 返回值。"""
    result = {
        "code": "sh600519",
        "query_days": 60,
        "earnings": [],
        "lockup": [],
        "dividend": [],
        "shareholder": [],
        "violation": [],
        "forecast": forecast_items or [],
    }
    result.update(kwargs)
    return result


class TestForecastScoring:
    """业绩预告评分。"""

    def test_no_forecast_neutral(self):
        """无预告数据时事件因子为中性 50。"""
        with patch("data.event.get_events", return_value=_make_events()):
            score = event_score("sh600519")
        assert score == 50.0

    def test_forecast_increase_big(self):
        """大幅预增（change_min > 100%）-> +15。"""
        forecast = [{
            "forecast_type": "increase",
            "change_min": 150,
            "change_max": 200,
        }]
        with patch("data.event.get_events", return_value=_make_events(forecast)):
            score = event_score("sh600519")
        assert score == 65.0  # 50 + 15

    def test_forecast_increase_moderate(self):
        """中幅预增（50-100%）-> +10。"""
        forecast = [{
            "forecast_type": "increase",
            "change_min": 60,
            "change_max": 80,
        }]
        with patch("data.event.get_events", return_value=_make_events(forecast)):
            score = event_score("sh600519")
        assert score == 60.0  # 50 + 10

    def test_forecast_increase_small(self):
        """小幅预增（<50%）-> +5。"""
        forecast = [{
            "forecast_type": "increase",
            "change_min": 20,
            "change_max": 40,
        }]
        with patch("data.event.get_events", return_value=_make_events(forecast)):
            score = event_score("sh600519")
        assert score == 55.0  # 50 + 5

    def test_forecast_loss(self):
        """预亏 -> -20。"""
        forecast = [{
            "forecast_type": "loss",
            "change_min": -100,
            "change_max": -50,
        }]
        with patch("data.event.get_events", return_value=_make_events(forecast)):
            score = event_score("sh600519")
        assert score == 30.0  # 50 - 20

    def test_forecast_continue_loss(self):
        """续亏 -> -15。"""
        forecast = [{"forecast_type": "continue_loss"}]
        with patch("data.event.get_events", return_value=_make_events(forecast)):
            score = event_score("sh600519")
        assert score == 35.0  # 50 - 15

    def test_forecast_decrease_big(self):
        """大幅预减（change_max < -50%）-> -12。"""
        forecast = [{
            "forecast_type": "decrease",
            "change_min": -80,
            "change_max": -60,
        }]
        with patch("data.event.get_events", return_value=_make_events(forecast)):
            score = event_score("sh600519")
        assert score == 38.0  # 50 - 12

    def test_forecast_decrease_small(self):
        """小幅预减 -> -5。"""
        forecast = [{
            "forecast_type": "decrease",
            "change_min": -30,
            "change_max": -10,
        }]
        with patch("data.event.get_events", return_value=_make_events(forecast)):
            score = event_score("sh600519")
        assert score == 45.0  # 50 - 5

    def test_forecast_turn_profit(self):
        """扭亏为盈 -> +12。"""
        forecast = [{"forecast_type": "turn_profit"}]
        with patch("data.event.get_events", return_value=_make_events(forecast)):
            score = event_score("sh600519")
        assert score == 62.0  # 50 + 12

    def test_forecast_continue_profit(self):
        """续盈 -> +3。"""
        forecast = [{"forecast_type": "continue_profit"}]
        with patch("data.event.get_events", return_value=_make_events(forecast)):
            score = event_score("sh600519")
        assert score == 53.0  # 50 + 3


class TestEventFactorActivation:
    """事件因子权重激活。"""

    def test_event_weight_nonzero_in_strategies(self):
        """(#10) 所有 6 策略 event 权重 > 0。"""
        from strategies import get_strategy

        for name in ["balanced", "quality_value", "growth_momentum",
                      "defensive", "turning_point", "ma_volume_momentum"]:
            weights = get_strategy(name)
            assert weights.get("event", 0) > 0, f"{name} event 权重应 > 0"

    def test_event_default_weight_nonzero(self):
        """(#10) event 因子 default_weight > 0。"""
        from strategies.factors.registry import get_factor

        factor = get_factor("event")
        assert factor.default_weight > 0

    def test_strategy_weights_sum_to_one(self):
        """策略权重归一化（和 ≈ 1.0）。"""
        from strategies import get_strategy

        for name in ["balanced", "quality_value", "growth_momentum",
                      "defensive", "turning_point", "ma_volume_momentum"]:
            weights = get_strategy(name)
            total = sum(v for k, v in weights.items()
                       if k not in ("label", "two_stage"))
            assert abs(total - 1.0) < 0.01, f"{name} 权重和 {total} 不等于 1.0"


class TestForecastFetcherFallback:
    """forecast fetcher 失败降级。"""

    def test_get_events_exception_returns_neutral(self):
        """get_events 抛异常时 event_score 返回中性 50。"""
        with patch("data.event.get_events", side_effect=Exception("network error")):
            score = event_score("sh600519")
        assert score == 50.0
