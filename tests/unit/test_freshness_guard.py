"""数据新鲜度断言单测（全 hermetic：固定时钟、不连网、不读运行时缓存）。

坏数据样本取自 2026-11-22 19:49–20:48 的真实报文：
- CBOE last_trade_time = 2026-11-20T16:15:01（美东 EST，周五收盘）
- CBOE 顶层 timestamp  = 2026-11-22 12:48:32（UTC，报文生成时刻，不是行情时间）
- 腾讯 usVIX 自带日期  = 2026-09-11 09:30:00（72 天前的旧值）
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from common.freshness import BEIJING, StaleDataError, assert_fresh, data_age_seconds, parse_quote_time

CBOE_QUOTE_TS = "2026-11-20T16:15:01"
CBOE_MSG_TS = "2026-11-22 12:48:32"
TENCENT_STALE_TS = "2026-09-11 09:30:00"
NOW = datetime(2026, 11, 22, 12, 49, tzinfo=timezone.utc)  # 北京 2026-11-22 20:49
WEEKEND_CHECK = datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc)  # 周一 08:30 北京巡检
FRESH_NOW = datetime(2026, 11, 20, 21, 30, tzinfo=timezone.utc)  # 报价后 15 分钟
MAX_AGE = timedelta(hours=48)


class TestParseQuoteTime:
    def test_cboe_last_trade_time_to_utc_and_beijing(self):
        quote = parse_quote_time(CBOE_QUOTE_TS)
        assert quote == datetime(2026, 11, 20, 21, 15, 1, tzinfo=timezone.utc)
        assert quote.astimezone(BEIJING).isoformat() == "2026-11-21T05:15:01+08:00"

    def test_message_stamp_parses_only_when_source_tz_explicitly_utc(self):
        # 顶层 timestamp 是 UTC 报文时刻；默认按美东解析会得到错误的 05:48 偏移
        assert parse_quote_time(CBOE_MSG_TS, source_tz=timezone.utc) == datetime(
            2026, 11, 22, 12, 48, 32, tzinfo=timezone.utc
        )

    @pytest.mark.parametrize("bad", [None, "", "   ", 0])
    def test_missing_timestamp_raises(self, bad):
        with pytest.raises(StaleDataError):
            parse_quote_time(bad)

    def test_unparseable_timestamp_raises(self):
        with pytest.raises(StaleDataError):
            parse_quote_time("not-a-time")


class TestFreshnessAssertion:
    def test_fresh_quote_passes(self):
        assert assert_fresh(CBOE_QUOTE_TS, max_age=MAX_AGE, now=FRESH_NOW) == datetime(
            2026, 11, 20, 21, 15, 1, tzinfo=timezone.utc
        )

    def test_weekend_quote_exceeds_threshold_raises(self):
        # 周一 08:30 北京巡检，周五 16:15 ET 报价已 51.25h —— 必须拒绝"当实时用"
        with pytest.raises(StaleDataError, match="数据年龄"):
            assert_fresh(CBOE_QUOTE_TS, max_age=MAX_AGE, now=WEEKEND_CHECK)

    def test_72_day_old_tencent_quote_raises(self):
        # 这是抓到的真坏数据：21.67 被旧代码盖上当天 as_of 冒充实时
        with pytest.raises(StaleDataError, match="数据年龄"):
            assert_fresh(TENCENT_STALE_TS, max_age=MAX_AGE, now=NOW)

    def test_future_timestamp_raises(self):
        with pytest.raises(StaleDataError, match="未来"):
            assert_fresh(CBOE_QUOTE_TS, max_age=MAX_AGE, now=FRESH_NOW - timedelta(hours=2))

    def test_data_age_seconds_is_positive_and_reports_hours(self):
        age = data_age_seconds(CBOE_QUOTE_TS, now=WEEKEND_CHECK)
        assert 51 * 3600 < age < 52 * 3600

    def test_naive_now_is_treated_as_utc(self):
        age = data_age_seconds(CBOE_QUOTE_TS, now=datetime(2026, 11, 20, 21, 30))
        assert age == 899  # 21:15:01 → 21:30:00
