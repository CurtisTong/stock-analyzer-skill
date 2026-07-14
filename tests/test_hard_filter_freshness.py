"""(#2) 财务数据时效性校验测试。

覆盖：
- 季报披露后数据未更新 -> stale
- 季报披露前数据正常 -> not stale
- grace 期内 -> not stale
- report_date 缺失 -> not stale（容错）
- _hard_filter 中 stale 时硬过滤降级为软警告
"""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from business.finance_freshness import (  # noqa: E402
    check_finance_freshness,
    _expected_latest_period,
)


class TestExpectedLatestPeriod:
    """应已披露的最近报告期反推。"""

    def test_july_expects_q1(self):
        """7 月：Q1(4/30 截止)和年报(4/30 截止)应已披露，最近是 Q1。"""
        today = date(2026, 7, 14)
        report_end, deadline = _expected_latest_period(today)
        # 7 月应已披露 Q1（截止 4/30），report_end="03-31"
        assert report_end == "03-31"

    def test_september_expects_half_year(self):
        """9 月：中报(8/31 截止)应已披露。"""
        today = date(2026, 9, 15)
        report_end, deadline = _expected_latest_period(today)
        assert report_end == "06-30"

    def test_november_expects_q3(self):
        """11 月：三季报(10/31 截止)应已披露。"""
        today = date(2026, 11, 15)
        report_end, deadline = _expected_latest_period(today)
        assert report_end == "09-30"

    def test_march_expects_annual(self):
        """3 月：上一年年报(次年 4/30 截止)尚未到截止日，但上上年年报应已披露。"""
        today = date(2026, 3, 15)
        report_end, deadline = _expected_latest_period(today)
        # 3 月 < 4/30 年报截止，最近已披露的是上一年 Q3（10/31 截止）
        assert report_end == "09-30"


class TestCheckFinanceFreshness:
    """check_finance_freshness 判定。"""

    def test_no_report_date_not_stale(self):
        """report_date 缺失时不判定（容错）。"""
        is_stale, msg = check_finance_freshness({}, today=date(2026, 7, 14))
        assert is_stale is False
        assert msg == ""

    def test_empty_report_date_not_stale(self):
        """report_date 为空字符串时不判定。"""
        is_stale, msg = check_finance_freshness(
            {"report_date": ""}, today=date(2026, 7, 14)
        )
        assert is_stale is False

    def test_unparseable_date_not_stale(self):
        """report_date 不可解析时不判定。"""
        is_stale, msg = check_finance_freshness(
            {"report_date": "invalid"}, today=date(2026, 7, 14)
        )
        assert is_stale is False

    def test_stale_q1_data_in_july(self):
        """7 月仍用上年年报数据 -> stale。

        7 月应已披露 Q1(03-31)，但 report_date 是去年年报(12-31) -> 过期。
        """
        fin = {"report_date": "2025-12-31"}  # 上年年报
        is_stale, msg = check_finance_freshness(fin, today=date(2026, 7, 14))
        assert is_stale is True
        assert "过期" in msg

    def test_fresh_q1_data_in_july(self):
        """7 月用 Q1 数据 -> not stale。"""
        fin = {"report_date": "2026-03-31"}  # 当年 Q1
        is_stale, msg = check_finance_freshness(fin, today=date(2026, 7, 14))
        assert is_stale is False

    def test_grace_period_not_stale(self):
        """截止日+grace 期内不判定过期。

        5/1（Q1 截止 4/30 + grace 7 天 = 5/7），5/1 在 grace 内 -> not stale。
        report_date=12-31（上年年报），虽然应已披露 Q1 但 grace 期内容忍。
        """
        fin = {"report_date": "2025-12-31"}
        is_stale, msg = check_finance_freshness(fin, today=date(2026, 5, 1))
        assert is_stale is False

    def test_after_grace_stale(self):
        """截止日+grace 后仍用旧数据 -> stale。

        5/10 > 5/7(4/30+7) -> 过期，report_date=12-31 < 03-31 -> stale。
        """
        fin = {"report_date": "2025-12-31"}
        is_stale, msg = check_finance_freshness(fin, today=date(2026, 5, 10))
        assert is_stale is True


class TestHardFilterFreshness:
    """_hard_filter 中 stale 时硬过滤降级为软警告。"""

    def _make_quote(self, code="sh600519", name="茅台", total_cap=100, amount=10000_0000, change_pct=0.5):
        return {
            "code": code,
            "name": name,
            "total_cap": total_cap,
            "amount": amount,
            "change_pct": change_pct,
        }

    def test_stale_loss_filter_downgraded(self):
        """财务过期时 EPS<0 降级为软警告（不在 reasons 中）。"""
        from business.screening_service import ScreeningService

        svc = ScreeningService()
        quote = self._make_quote()
        fin = {"report_date": "2025-12-31", "eps": -0.5}  # 亏损 + 过期

        with patch("business.finance_freshness.check_finance_freshness",
                   return_value=(True, "财报数据过期")):
            reasons, warnings = svc._hard_filter(quote, fin, {})

        # EPS<0 应在 warnings 中而非 reasons
        assert not any("EPS<0" in r for r in reasons)
        assert any("EPS" in w and "亏损" in w for w in warnings)

    def test_fresh_loss_filter_rejects(self):
        """财务新鲜时 EPS<0 仍硬拒绝。"""
        from business.screening_service import ScreeningService

        svc = ScreeningService()
        quote = self._make_quote()
        fin = {"report_date": "2026-03-31", "eps": -0.5}  # 亏损 + 新鲜

        with patch("business.finance_freshness.check_finance_freshness",
                   return_value=(False, "")):
            reasons, warnings = svc._hard_filter(quote, fin, {})

        assert any("EPS<0" in r for r in reasons)

    def test_stale_goodwill_downgraded(self):
        """财务过期时商誉过高降级为软警告。"""
        from business.screening_service import ScreeningService

        svc = ScreeningService()
        quote = self._make_quote()
        fin = {"report_date": "2025-12-31", "eps": 1.0, "goodwill_ratio": 50}

        with patch("business.finance_freshness.check_finance_freshness",
                   return_value=(True, "财报数据过期")):
            reasons, warnings = svc._hard_filter(quote, fin, {})

        assert not any("商誉" in r for r in reasons)
        assert any("商誉" in w for w in warnings)

    def test_stale_pledge_downgraded(self):
        """财务过期时质押过高降级为软警告。"""
        from business.screening_service import ScreeningService

        svc = ScreeningService()
        quote = self._make_quote()
        fin = {"report_date": "2025-12-31", "eps": 1.0, "pledge_ratio": 80}

        with patch("business.finance_freshness.check_finance_freshness",
                   return_value=(True, "财报数据过期")):
            reasons, warnings = svc._hard_filter(quote, fin, {})

        assert not any("质押" in r for r in reasons)
        assert any("质押" in w for w in warnings)

    def test_stale_warning_includes_message(self):
        """过期警告包含过期说明信息。"""
        from business.screening_service import ScreeningService

        svc = ScreeningService()
        quote = self._make_quote()
        fin = {"report_date": "2025-12-31", "eps": -0.5}

        with patch("business.finance_freshness.check_finance_freshness",
                   return_value=(True, "财报数据过期(report_date=2025-12-31)")):
            reasons, warnings = svc._hard_filter(quote, fin, {})

        assert any("财报数据过期" in w for w in warnings)
