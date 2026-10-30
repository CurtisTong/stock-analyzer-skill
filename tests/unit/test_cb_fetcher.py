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

    def test_truncated_when_pages_capped(self, monkeypatch):
        """总页数超过 MAX_PAGES 时 truncated 必须为 True（off-by-one 回归锚点）。"""
        import fetchers.cb.eastmoney_cb as mod
        from fetchers.cb.eastmoney_cb import ConvertibleBondFetcher

        # 3 页数据（total=300），MAX_PAGES 压到 2 → 只取 200 条且必须告警截断
        monkeypatch.setattr(mod, "MAX_PAGES", 2)
        pages = {
            1: _resp([_row(code=f"P1{i}") for i in range(100)], total=300),
            2: _resp([_row(code=f"P2{i}") for i in range(100)], total=300),
            3: _resp([_row(code=f"P3{i}") for i in range(100)], total=300),
        }

        def _http_get(url, headers=None, timeout=10, max_retries=3):
            page = int(url.split("pn=")[1].split("&")[0])
            return json.dumps(pages[page]).encode("utf-8")

        monkeypatch.setattr(mod, "http_get_with_headers", _http_get)
        r = ConvertibleBondFetcher().fetch(top=500)
        assert len(r["items"]) == 200
        assert r["truncated"] is True

    def test_zero_double_low_not_treated_as_missing(self, monkeypatch):
        """双低值恰为 0.0 是极端合法值，不得被 or 兜底当成缺失挤到末尾。"""
        f = self._fetcher(
            monkeypatch,
            _resp(
                [
                    _row(code="A", price=100.0, premium=-100.0),  # 双低 0.0
                    _row(code="B", price=80.0, premium=-5.0),  # 双低 75
                ]
            ),
        )
        r = f.fetch(top=10)
        assert [i["code"] for i in r["items"]] == ["A", "B"]

    def test_provider_matches_yaml_key(self):
        from fetchers.cb.eastmoney_cb import ConvertibleBondFetcher

        assert ConvertibleBondFetcher().provider == "eastmoney"
