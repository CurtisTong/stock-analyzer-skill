"""可转债 fetcher 单元测试（v1.24.0）。"""

from __future__ import annotations

import json

import pytest


def _resp(rows, total=None):
    return {"rc": 0, "data": {"total": total if total is not None else len(rows), "diff": rows}}


def _row(code="123291", name="佐力转债", price=118.0, chg=1.2, premium=-6.81):
    return {"f2": price, "f3": chg, "f12": code, "f14": name, "f127": premium}


class TestConvertibleBondFetcher:
    def _fetcher(self, monkeypatch, response):
        import fetchers.cb.eastmoney_cb as mod
        from fetchers.cb.eastmoney_cb import ConvertibleBondFetcher

        def _http_get(url, headers=None, timeout=10, max_retries=3):
            if isinstance(response, (bytes, bytearray)):
                return response
            return json.dumps(response).encode("utf-8")

        monkeypatch.setattr(mod, "http_get_with_headers", _http_get)
        return ConvertibleBondFetcher()

    def test_parse_and_double_low(self, monkeypatch):
        f = self._fetcher(
            monkeypatch,
            _resp(
                [
                    _row(code="118027", name="宏图转债", price=76.488, premium=-6.81),
                    _row(code="110081", name="闻泰转债", price=90.89, premium=-0.39),
                ]
            ),
        )
        r = f.fetch(top=5)
        assert r["type"] == "cb_quote"
        assert len(r["items"]) == 2
        hongtu = r["items"][0]
        assert hongtu["code"] == "118027"
        assert hongtu["premium_ratio"] == -6.81
        # 双低 = 价格 + 溢价率数值（76.488 - 6.81 = 69.68）
        assert hongtu["double_low"] == pytest.approx(69.68, abs=0.01)

    def test_none_premium_stays_none(self, monkeypatch):
        f = self._fetcher(monkeypatch, _resp([_row(code="110092", premium="-")]))
        r = f.fetch()
        assert r["items"][0]["premium_ratio"] is None
        assert r["items"][0]["double_low"] is None

    def test_inactive_bond_filtered(self, monkeypatch):
        """价格 0（未上市/摘牌）不进入列表。"""
        f = self._fetcher(monkeypatch, _resp([_row(price=0.0), _row(code="110081", price=90.0)]))
        r = f.fetch()
        assert len(r["items"]) == 1
        assert r["items"][0]["code"] == "110081"

    def test_sorted_by_double_low(self, monkeypatch):
        f = self._fetcher(
            monkeypatch,
            _resp(
                [
                    _row(code="A", price=120.0, premium=10.0),  # 双低 130
                    _row(code="B", price=80.0, premium=-5.0),  # 双低 75
                    _row(code="C", price=100.0, premium=2.0),  # 双低 102
                ]
            ),
        )
        r = f.fetch(top=10)
        codes = [i["code"] for i in r["items"]]
        assert codes == ["B", "C", "A"]  # 双低升序

    def test_code_filter(self, monkeypatch):
        f = self._fetcher(monkeypatch, _resp([_row(), _row(code="110081", price=90.0)]))
        r = f.fetch(code="sh123291")
        assert len(r["items"]) == 1
        assert r["items"][0]["code"] == "123291"

    def test_network_error_propagates(self, monkeypatch):
        import fetchers.cb.eastmoney_cb as mod
        from fetchers.cb.eastmoney_cb import ConvertibleBondFetcher
        from common.exceptions import NetworkError

        def _boom(url, headers=None, timeout=10, max_retries=3):
            raise NetworkError(url, "forbidden")

        monkeypatch.setattr(mod, "http_get_with_headers", _boom)
        with pytest.raises(NetworkError):
            ConvertibleBondFetcher().fetch()
