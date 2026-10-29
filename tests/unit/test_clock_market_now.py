"""market_now 时区口径测试（v1.24.0 复审修复）。

背景：aa1d43e 修了涨停时间戳渲染时区，但"今天是哪天"仍取 runner 本地时区——
UTC 主机上北京 00:00-08:00 会请求错交易日。market_now 统一收口该口径。
"""

from __future__ import annotations

from datetime import datetime


class TestMarketNow:
    def test_frozen_naive_interpreted_as_beijing_wall(self, monkeypatch):
        """冻结的无参时钟（naive）按北京墙上钟解释，日期不漂移。"""
        from dev import clock

        monkeypatch.setattr(clock, "_now_func", lambda: datetime(2026, 10, 29, 17, 0))
        dt = clock.market_now()
        assert (dt.year, dt.month, dt.day, dt.hour) == (2026, 10, 29, 17)
        assert dt.utcoffset().total_seconds() == 8 * 3600

    def test_real_now_is_aware_beijing(self):
        """生产路径：返回带 +8 时区的 aware datetime。"""
        from dev import clock

        dt = clock.market_now()
        assert dt.tzinfo is not None
        assert dt.utcoffset().total_seconds() == 8 * 3600

    def test_freeze_fixture_compatible(self, freeze_time):
        """conftest 的 freeze_time（无参 lambda）不破坏 market_now。"""
        from dev import clock

        freeze_time("2026-07-20 10:30:00")
        dt = clock.market_now()
        assert (dt.year, dt.month, dt.day) == (2026, 7, 20)
