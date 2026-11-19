"""宏观三个字段的补充数据源（fix/macro-extra-sources）。

- 美元指数：新浪 DINIW（指数点）
- 美债 10Y：东财数据中心 RPTA_WEB_TREASURYYIELD（百分数，取最近非 null 行）
- VIX：CBOE 官方延迟报价（指数点，延迟 15 分钟，必须标 delay_minutes）

每个源失败都不抛，链条末端返回 None 并由 fetch_all 记 degraded_fields。
全部 monkeypatch，不连网。
"""

from __future__ import annotations

import io
import json

import pytest

import macro_indicators as mi


@pytest.fixture(autouse=True)
def _isolated_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(mi, "SNAPSHOT_PATH", tmp_path / "macro_snapshot.json")
    monkeypatch.setattr(mi, "_load_snapshot", lambda: {})
    monkeypatch.setattr(mi, "_save_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(mi, "_key_is_fresh", lambda *a, **k: False)


def _fake_urlopen(payload: str):
    class _Resp(io.BytesIO):
        def read(self, *a, **k):
            return payload.encode("utf-8")

    return lambda *a, **k: _Resp()


class TestEastmoneyTreasury:
    def test_skips_null_latest_row(self, monkeypatch):
        """最新日未更新（null）时必须向前找最近非空行，不能返回 None。"""
        rows = {
            "result": {
                "data": [
                    {"SOLAR_DATE": "2026-11-19 00:00:00", "EMG00001310": None},
                    {"SOLAR_DATE": "2026-11-18 00:00:00", "EMG00001310": 5.07},
                ]
            }
        }
        monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen(json.dumps(rows)))
        assert mi._eastmoney_treasury_10y() == (5.07, "2026-11-18")

    def test_all_null_returns_none(self, monkeypatch):
        rows = {"result": {"data": [{"SOLAR_DATE": "2026-11-19", "EMG00001310": None}]}}
        monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen(json.dumps(rows)))
        assert mi._eastmoney_treasury_10y() is None

    def test_network_error_returns_none(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("blocked")

        monkeypatch.setattr("urllib.request.urlopen", boom)
        assert mi._eastmoney_treasury_10y() is None


class TestVixCboe:
    def test_parses_current_price(self, monkeypatch):
        payload = {"timestamp": "2026-11-19 14:40:24", "data": {"current_price": 22.5, "close": 24.56}}
        monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen(json.dumps(payload)))
        assert mi._cboe_vix() == (22.5, "2026-11-19 14:40:24")

    def test_missing_field_returns_none(self, monkeypatch):
        monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen(json.dumps({"data": {}})))
        assert mi._cboe_vix() is None

    def test_network_error_returns_none(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("blocked")

        monkeypatch.setattr("urllib.request.urlopen", boom)
        assert mi._cboe_vix() is None


class TestFetchChains:
    def test_treasury_yfinance_ok_skips_eastmoney(self, monkeypatch):
        called = []
        monkeypatch.setattr(mi, "_yfinance_get", lambda *a, **k: 4.95)
        monkeypatch.setattr(mi, "_eastmoney_treasury_10y", lambda: called.append(1) or (5.0, "2026-11-18"))
        out = mi.fetch_treasury_10y()
        assert out["source"] == "yfinance"
        assert out["value"] == 4.95
        assert called == []

    def test_treasury_falls_back_to_eastmoney(self, monkeypatch):
        monkeypatch.setattr(mi, "_yfinance_get", lambda *a, **k: None)
        monkeypatch.setattr(mi, "_eastmoney_treasury_10y", lambda: (5.07, "2026-11-18"))
        out = mi.fetch_treasury_10y()
        assert out["value"] == 5.07
        assert out["source"] == "eastmoney_treasury"
        assert out["as_of"].startswith("2026-11-18")

    def test_treasury_both_fail_returns_none(self, monkeypatch):
        monkeypatch.setattr(mi, "_yfinance_get", lambda *a, **k: None)
        monkeypatch.setattr(mi, "_eastmoney_treasury_10y", lambda: None)
        assert mi.fetch_treasury_10y() is None

    def test_vix_falls_back_to_cboe_with_delay_marker(self, monkeypatch):
        monkeypatch.setattr(mi, "_yfinance_get", lambda *a, **k: None)
        monkeypatch.setattr(mi, "_cboe_vix", lambda: (22.42, "2026-11-19 14:46:24"))
        monkeypatch.setattr(mi, "_tencent_us_index_get", lambda sym: pytest.fail("CBOE 成功时不应再问腾讯"))
        out = mi.fetch_vix()
        assert out["value"] == 22.42
        assert out["source"] == "cboe_delayed"
        assert out["delay_minutes"] == 15
        assert out["as_of"] == "2026-11-19 14:46:24"

    def test_vix_falls_back_to_tencent_when_cboe_fails(self, monkeypatch):
        monkeypatch.setattr(mi, "_yfinance_get", lambda *a, **k: None)
        monkeypatch.setattr(mi, "_cboe_vix", lambda: None)
        monkeypatch.setattr(mi, "_tencent_us_index_get", lambda sym: 21.67)
        out = mi.fetch_vix()
        assert out["source"] == "tencent_us_index"
        assert "delay_minutes" not in out

    def test_vix_all_fail_returns_none(self, monkeypatch):
        monkeypatch.setattr(mi, "_yfinance_get", lambda *a, **k: None)
        monkeypatch.setattr(mi, "_cboe_vix", lambda: None)
        monkeypatch.setattr(mi, "_tencent_us_index_get", lambda sym: None)
        assert mi.fetch_vix() is None


class TestDegradedMarking:
    def test_treasury_and_vix_land_in_degraded_fields(self, monkeypatch):
        monkeypatch.setattr(mi, "_yfinance_get", lambda *a, **k: None)
        monkeypatch.setattr(mi, "_eastmoney_treasury_10y", lambda: None)
        monkeypatch.setattr(mi, "_cboe_vix", lambda: None)
        monkeypatch.setattr(mi, "_tencent_us_index_get", lambda sym: None)
        for name in (
            "fetch_margin_total",
            "fetch_if_basis",
            "fetch_ic_basis",
            "fetch_ih_basis",
            "fetch_erp_sh300",
            "fetch_lithium",
            "fetch_polyethylene",
            "fetch_polypropylene",
        ):
            monkeypatch.setattr(mi, name, lambda *a, **k: None, raising=False)

        data = mi.fetch_all()

        assert "macro.treasury_10y_pct" in data["data_quality"]["degraded_fields"]
        assert "macro.vix" in data["data_quality"]["degraded_fields"]
        assert data["macro"]["treasury_10y_pct_source"] is None
