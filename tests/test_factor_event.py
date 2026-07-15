"""事件因子评分测试（v2.7.x 覆盖率提升）。

mock data.event.get_events，覆盖 5 个事件维度。
"""

import sys
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def _future_date(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")


def _past_date(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


class TestEventScore:
    """event_score 五维度评分。"""

    def test_no_events_returns_neutral(self):
        """无事件数据返回中性分 50。"""
        with patch("data.event.get_events", return_value={}):
            from strategies.factors.event import event_score

            assert event_score("sh600519") == 50.0

    def test_fetch_exception_returns_neutral(self):
        """get_events 抛异常时返回中性分。"""
        with patch("data.event.get_events", side_effect=Exception("network")):
            from strategies.factors.event import event_score

            assert event_score("sh600519") == 50.0

    def test_lockup_large_cap_deduction(self):
        """大额解禁（>50 亿）扣 20 分。"""
        events = {"lockup": [{"free_date": _future_date(10), "lift_market_cap": 60}]}
        with patch("data.event.get_events", return_value=events):
            from strategies.factors.event import event_score

            assert event_score("sh600519") == 30.0

    def test_lockup_medium_cap_deduction(self):
        """中额解禁（20-50 亿）扣 12 分。"""
        events = {"lockup": [{"free_date": _future_date(10), "lift_market_cap": 30}]}
        with patch("data.event.get_events", return_value=events):
            from strategies.factors.event import event_score

            assert event_score("sh600519") == 38.0

    def test_lockup_small_cap_deduction(self):
        """小额解禁扣 5 分。"""
        events = {"lockup": [{"free_date": _future_date(10), "lift_market_cap": 10}]}
        with patch("data.event.get_events", return_value=events):
            from strategies.factors.event import event_score

            assert event_score("sh600519") == 45.0

    def test_lockup_far_future_no_impact(self):
        """解禁在 30 天后不影响评分。"""
        events = {"lockup": [{"free_date": _future_date(60), "lift_market_cap": 60}]}
        with patch("data.event.get_events", return_value=events):
            from strategies.factors.event import event_score

            assert event_score("sh600519") == 50.0

    def test_dividend_high_bonus_addition(self):
        """高分红（>1.0）加 10 分。"""
        events = {"dividend": [{"ex_date": _future_date(10), "bonus_per_share": 1.5}]}
        with patch("data.event.get_events", return_value=events):
            from strategies.factors.event import event_score

            assert event_score("sh600519") == 60.0

    def test_dividend_medium_bonus_addition(self):
        """中分红（0.3-1.0）加 5 分。"""
        events = {"dividend": [{"ex_date": _future_date(10), "bonus_per_share": 0.5}]}
        with patch("data.event.get_events", return_value=events):
            from strategies.factors.event import event_score

            assert event_score("sh600519") == 55.0

    def test_earnings_before_deduction(self):
        """财报前 7 天内观望扣 3 分。"""
        events = {"earnings": [{"disclosure_date": _future_date(3)}]}
        with patch("data.event.get_events", return_value=events):
            from strategies.factors.event import event_score

            assert event_score("sh600519") == 47.0

    def test_earnings_after_addition(self):
        """财报刚披露后（7 天内）加 3 分。"""
        events = {"earnings": [{"disclosure_date": _past_date(3)}]}
        with patch("data.event.get_events", return_value=events):
            from strategies.factors.event import event_score

            assert event_score("sh600519") == 53.0

    def test_shareholder_large_buy_addition(self):
        """大比例增持（>1%）加 15 分。"""
        events = {"shareholder": [{"end_date": _past_date(30), "change_ratio": 1.5}]}
        with patch("data.event.get_events", return_value=events):
            from strategies.factors.event import event_score

            assert event_score("sh600519") == 65.0

    def test_shareholder_large_sell_deduction(self):
        """大比例减持（<-1%）扣 15 分。"""
        events = {"shareholder": [{"end_date": _past_date(30), "change_ratio": -1.5}]}
        with patch("data.event.get_events", return_value=events):
            from strategies.factors.event import event_score

            assert event_score("sh600519") == 35.0

    def test_violation_investigation_deduction(self):
        """立案调查扣 30 分。"""
        events = {"violation": [{"punish_date": _past_date(30), "content": "立案调查"}]}
        with patch("data.event.get_events", return_value=events):
            from strategies.factors.event import event_score

            assert event_score("sh600519") == 20.0

    def test_violation_penalty_deduction(self):
        """行政处罚扣 15 分。"""
        events = {"violation": [{"punish_date": _past_date(30), "content": "罚款处罚"}]}
        with patch("data.event.get_events", return_value=events):
            from strategies.factors.event import event_score

            assert event_score("sh600519") == 35.0

    def test_violation_warning_deduction(self):
        """轻微警示扣 5 分。"""
        events = {"violation": [{"punish_date": _past_date(30), "reason": "警示函"}]}
        with patch("data.event.get_events", return_value=events):
            from strategies.factors.event import event_score

            assert event_score("sh600519") == 45.0

    def test_combined_events(self):
        """多事件叠加：解禁扣 20 + 分红加 10 = 40。"""
        events = {
            "lockup": [{"free_date": _future_date(10), "lift_market_cap": 60}],
            "dividend": [{"ex_date": _future_date(5), "bonus_per_share": 1.5}],
        }
        with patch("data.event.get_events", return_value=events):
            from strategies.factors.event import event_score

            assert event_score("sh600519") == 40.0


class TestDaysBetween:
    """_days_between 工具函数。"""

    def test_normal_case(self):
        from strategies.factors.event import _days_between

        assert _days_between("2026-01-01", "2026-01-11") == 10

    def test_negative_case(self):
        from strategies.factors.event import _days_between

        assert _days_between("2026-01-11", "2026-01-01") == -10

    def test_invalid_date(self):
        from strategies.factors.event import _days_between

        assert _days_between("invalid", "2026-01-01") == -999

    def test_none_input(self):
        from strategies.factors.event import _days_between

        assert _days_between(None, "2026-01-01") == -999

    def test_long_date_string(self):
        """带时间部分的日期字符串截取前 10 位。"""
        from strategies.factors.event import _days_between

        assert _days_between("2026-01-01 12:00:00", "2026-01-02 08:00:00") == 1
