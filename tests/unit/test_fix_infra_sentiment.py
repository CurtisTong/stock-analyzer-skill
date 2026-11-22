"""2026-11-21 code review §4.1 情绪面板缓存回归。

按 date 做 key 却共用单一 _cache_ts：拉新日期会刷新全局时间戳，
让早已过期的旧日期缓存无限续期；且读写无锁。现在逐条判定 TTL。
"""

from __future__ import annotations

import time

import pytest

import data.sentiment_panel as panel


@pytest.fixture(autouse=True)
def _isolated_panel(monkeypatch):
    panel._cache = {}
    panel._cache_ts = 0.0
    calls: list[tuple[str, str]] = []

    def fake_fetch(endpoint, date):
        calls.append((endpoint, date))
        return [{"c": "600519", "n": "茅台", "hybk": "白酒", "lbc": 1}]

    monkeypatch.setattr(panel, "_fetch_pool", fake_fetch)
    return calls


class TestPerDateCacheTTL:
    def test_same_date_within_ttl_hits_cache(self, _isolated_panel):
        panel.refresh_panel(date="20261020")
        calls_after_first = len(_isolated_panel)
        panel.refresh_panel(date="20261020")
        assert len(_isolated_panel) == calls_after_first

    def test_new_date_does_not_extend_old_date_cache(self, _isolated_panel):
        """拉新日期刷新全局时间戳后，旧日期过期缓存必须重新拉取。"""
        old = time.time() - panel._CACHE_TTL - 10
        panel._cache["20261020"] = ({"date": "20261020", "stocks": {}}, old)
        panel._cache_ts = time.time()  # 模拟刚拉过新日期的全局戳

        panel.refresh_panel(date="20261021")
        calls_before_old = len(_isolated_panel)
        result = panel.refresh_panel(date="20261020")

        assert len(_isolated_panel) > calls_before_old, "旧日期缓存不应被新日期无限续期"
        assert result["date"] == "20261020"

    def test_cache_entry_carries_own_timestamp(self, _isolated_panel):
        panel.refresh_panel(date="20261020")
        entry = panel._cache["20261020"]
        assert isinstance(entry, tuple) and len(entry) == 2
        assert isinstance(entry[1], float)
