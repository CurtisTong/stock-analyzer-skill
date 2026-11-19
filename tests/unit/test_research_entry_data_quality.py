"""research 入口（announcements / events）的数据完整性信封（P0-4b）。

口径：这两个入口没有"行情域"概念，只有"取数是否失败"：
- 取到数据 → ok
- 空结果但没报错 → **ok**（真没公告/事件，不是降级）
- 解析失败/网络失败 → failed + conclusions_allowed=False

全部 monkeypatch，不连网。
"""

from __future__ import annotations

import announcements
import events
from common import data_quality as dq


class TestAnnouncementsEnvelope:
    def test_ok_with_items(self, monkeypatch):
        monkeypatch.setattr(announcements, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(announcements, "cache_set", lambda *a, **k: None)
        monkeypatch.setattr(
            announcements,
            "http_get",
            lambda *a, **k: '{"data": {"list": [{"title": "分红公告"}]}}',
        )
        data = announcements.fetch_announcements("sh600519", use_cache=False)
        payload = announcements._data_quality_payload(data)
        assert payload["data_quality"]["status"] == "ok"
        assert payload["data_quality"]["conclusions_allowed"] is True
        assert payload["rows"][0]["title"] == "分红公告"

    def test_empty_is_ok_not_degraded(self, monkeypatch):
        monkeypatch.setattr(announcements, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(announcements, "cache_set", lambda *a, **k: None)
        monkeypatch.setattr(announcements, "http_get", lambda *a, **k: '{"data": {"list": []}}')
        data = announcements.fetch_announcements("sh600519", use_cache=False)
        payload = announcements._data_quality_payload(data)
        assert data == []
        assert payload["data_quality"]["status"] == "ok"

    def test_json_decode_error_is_failed(self, monkeypatch):
        monkeypatch.setattr(announcements, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(announcements, "cache_set", lambda *a, **k: None)
        monkeypatch.setattr(announcements, "http_get", lambda *a, **k: "<html>not json</html>")
        data = announcements.fetch_announcements("sh600519", use_cache=False)
        payload = announcements._data_quality_payload(data)
        assert payload["data_quality"]["status"] == "failed"
        assert payload["data_quality"]["missing_domains"] == ["announcement"]
        assert payload["data_quality"]["conclusions_allowed"] is False
        header = dq.render_header(payload["data_quality"])
        assert "⚠️" in header


class TestEventsEnvelope:
    def test_ok_payload(self, monkeypatch):
        monkeypatch.setattr(events, "get_events", lambda code, days: {"events": [], "summary": "无"})
        events._LAST_DEGRADED["reason"] = None
        payload = events._data_quality_payload({"events": [], "summary": "无"})
        assert payload["data_quality"]["status"] == "ok"
        assert payload["data_quality"]["conclusions_allowed"] is True

    def test_failed_payload(self):
        events._LAST_DEGRADED["reason"] = "events.network"
        try:
            payload = events._data_quality_payload({"events": [], "summary": "无"})
        finally:
            events._LAST_DEGRADED["reason"] = None
        assert payload["data_quality"]["status"] == "failed"
        assert payload["data_quality"]["missing_domains"] == ["event"]
        assert payload["data_quality"]["conclusions_allowed"] is False
