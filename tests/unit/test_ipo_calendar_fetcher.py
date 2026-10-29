"""新股日历 fetcher 单元测试（v1.24.0）。"""

from __future__ import annotations

import json

import pytest


def _response(rows):
    return {"success": True, "result": {"pages": 1, "data": rows}}


def _row(code="688827", name="钶锐锶", date="2026-11-02 00:00:00", dtype="缴款日", stype="0"):
    return {
        "SECURITY_CODE": code,
        "SECURITY_NAME_ABBR": name,
        "TRADE_DATE": date,
        "DATE_TYPE": dtype,
        "SECURITY_TYPE": stype,
    }


class TestIpoCalendarFetcher:
    def _fetcher(self, monkeypatch, response):
        import fetchers.ipo.eastmoney_ipo as mod
        from fetchers.ipo.eastmoney_ipo import IpoCalendarFetcher

        def _http_get(url, timeout=10, max_retries=3):
            if isinstance(response, (bytes, bytearray)):
                return response
            return json.dumps(response).encode("utf-8")

        monkeypatch.setattr(mod, "http_get", _http_get)
        return IpoCalendarFetcher()

    def test_parse_fields(self, monkeypatch):
        f = self._fetcher(
            monkeypatch,
            _response(
                [
                    _row(),
                    _row(code="123289", name="中科转债", dtype="上市", stype="1"),
                ]
            ),
        )
        r = f.fetch(days=7)
        assert r["type"] == "ipo_calendar"
        assert len(r["items"]) == 2
        stock = r["items"][0]
        assert stock["code"] == "688827"
        assert stock["date"] == "2026-11-02"
        assert stock["event_type"] == "缴款日"
        assert stock["security_type"] == "股票"
        bond = r["items"][1]
        assert bond["security_type"] == "债券"  # SECURITY_TYPE=1 → 债券

    def test_code_filter(self, monkeypatch):
        f = self._fetcher(
            monkeypatch,
            _response([_row(), _row(code="123289", name="中科转债", stype="1")]),
        )
        r = f.fetch(code="sh688827", days=7)
        assert len(r["items"]) == 1
        assert r["items"][0]["code"] == "688827"

    def test_code_filter_no_match_returns_none(self, monkeypatch):
        f = self._fetcher(monkeypatch, _response([_row()]))
        assert f.fetch(code="sh600519") is None

    def test_empty_result_returns_none(self, monkeypatch):
        f = self._fetcher(monkeypatch, {"success": True, "result": {"pages": 1, "data": []}})
        assert f.fetch() is None

    def test_network_error_propagates(self, monkeypatch):
        import fetchers.ipo.eastmoney_ipo as mod
        from fetchers.ipo.eastmoney_ipo import IpoCalendarFetcher
        from common.exceptions import NetworkError

        def _boom(url, timeout=10, max_retries=3):
            raise NetworkError(url, "timeout")

        monkeypatch.setattr(mod, "http_get", _boom)
        with pytest.raises(NetworkError):
            IpoCalendarFetcher().fetch()
