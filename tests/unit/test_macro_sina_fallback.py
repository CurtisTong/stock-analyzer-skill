"""宏观指标的新浪外盘兜底（fix/macro-sina-fallback）。

背景：yfinance 被 Yahoo 限流后，黄金/WTI/布伦特/离岸人民币在盘后巡检里全是降级。
新浪外盘（hf_* / fx_s*）2026-11-19 实测可用，作为第二数据源。

三条路径必须都覆盖（全部 monkeypatch，不连网）：
1. yfinance 成功 → 不触碰新浪；
2. yfinance 失败 → 新浪成功，source=sina_foreign、单位与 yfinance 同口径；
3. 两条都失败 → None（无 fixture 时），fetch_all 记 degraded_fields。
"""

from __future__ import annotations

import pytest

import macro_indicators as mi


@pytest.fixture(autouse=True)
def _isolated_snapshot(monkeypatch, tmp_path):
    """隔离 snapshot 文件，避免读到本机真实缓存。"""
    monkeypatch.setattr(mi, "SNAPSHOT_PATH", tmp_path / "macro_snapshot.json")
    monkeypatch.setattr(mi, "_load_snapshot", lambda: {})
    monkeypatch.setattr(mi, "_save_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(mi, "_key_is_fresh", lambda *a, **k: False)


class TestCommodityFallback:
    def test_yfinance_ok_skips_sina(self, monkeypatch):
        called = []
        monkeypatch.setattr(mi, "_yfinance_get", lambda symbol, value_attr="last_price": 3700.0)
        monkeypatch.setattr(mi, "_sina_foreign_get", lambda symbol: called.append(symbol) or 1.0)

        out = mi.fetch_gold()

        assert out["value"] == 3700.0
        assert out["source"] == "yfinance"
        assert called == [], "yfinance 成功时不得再请求新浪"

    def test_yfinance_fails_falls_back_to_sina(self, monkeypatch):
        monkeypatch.setattr(mi, "_yfinance_get", lambda *a, **k: None)
        monkeypatch.setattr(mi, "_sina_foreign_get", lambda symbol: 83.62)

        out = mi.fetch_wti_oil()

        assert out["value"] == 83.62
        assert out["source"] == "sina_foreign"
        assert out["symbol"] == "CL=F"

    def test_both_fail_returns_none(self, monkeypatch):
        monkeypatch.setattr(mi, "_yfinance_get", lambda *a, **k: None)
        monkeypatch.setattr(mi, "_sina_foreign_get", lambda symbol: None)

        assert mi.fetch_brent_oil() is None


class TestUsdCnyFallback:
    def test_falls_back_to_sina_fx(self, monkeypatch):
        monkeypatch.setattr(mi, "_yfinance_get", lambda *a, **k: None)
        monkeypatch.setattr(mi, "_sina_foreign_get", lambda symbol: 6.6693)

        out = mi.fetch_usd_cny()

        assert out["value"] == 6.6693
        assert out["source"] == "sina_foreign"

    def test_both_fail_returns_none(self, monkeypatch):
        monkeypatch.setattr(mi, "_yfinance_get", lambda *a, **k: None)
        monkeypatch.setattr(mi, "_sina_foreign_get", lambda symbol: None)
        assert mi.fetch_usd_cny() is None


class TestSinaSymbolMapping:
    def test_mapping_is_yfinance_ticker_keyed(self):
        assert mi._SINA_FOREIGN_SYMBOLS["GC=F"] == ("hf_GC", 0)
        assert mi._SINA_FOREIGN_SYMBOLS["CL=F"] == ("hf_CL", 0)
        assert mi._SINA_FOREIGN_SYMBOLS["BZ=F"] == ("hf_OIL", 0)
        assert mi._SINA_FOREIGN_SYMBOLS["CNY=X"] == ("fx_susdcnh", 1)

    def test_unmapped_symbol_returns_none_without_network(self, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("未映射的 symbol 不应发起请求")

        monkeypatch.setattr("urllib.request.urlopen", boom)
        assert mi._sina_foreign_get("^VIX") is None

    def test_network_error_does_not_raise(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("network down")

        monkeypatch.setattr("urllib.request.urlopen", boom)
        assert mi._sina_foreign_get("GC=F") is None


class TestUsdIndexFallback:
    def test_yfinance_ok_skips_sina(self, monkeypatch):
        called = []
        monkeypatch.setattr(mi, "_yfinance_get", lambda *a, **k: 103.5)
        monkeypatch.setattr(mi, "_sina_foreign_get", lambda sym: called.append(sym) or 1.0)
        out = mi.fetch_usd_index()
        assert out["source"] == "yfinance"
        assert called == []

    def test_yfinance_fails_falls_back_to_sina_diniw(self, monkeypatch):
        monkeypatch.setattr(mi, "_yfinance_get", lambda *a, **k: None)
        monkeypatch.setattr(mi, "_sina_foreign_get", lambda sym: 103.6823)
        out = mi.fetch_usd_index()
        assert out["value"] == 103.68
        assert out["source"] == "sina_foreign"

    def test_both_fail_returns_none(self, monkeypatch):
        monkeypatch.setattr(mi, "_yfinance_get", lambda *a, **k: None)
        monkeypatch.setattr(mi, "_sina_foreign_get", lambda sym: None)
        assert mi.fetch_usd_index() is None


class TestVixFallback:
    def test_yfinance_fails_falls_back_to_tencent(self, monkeypatch):
        monkeypatch.setattr(mi, "_yfinance_get", lambda *a, **k: None)
        monkeypatch.setattr(mi, "_tencent_us_index_get", lambda sym: 21.67)
        out = mi.fetch_vix()
        assert out["value"] == 21.67
        assert out["source"] == "tencent_us_index"

    def test_both_fail_returns_none(self, monkeypatch):
        monkeypatch.setattr(mi, "_yfinance_get", lambda *a, **k: None)
        monkeypatch.setattr(mi, "_tencent_us_index_get", lambda sym: None)
        assert mi.fetch_vix() is None

    def test_tencent_unmapped_symbol_returns_none(self):
        assert mi._tencent_us_index_get("^GSPC") is None


class TestDegradedMarking:
    def test_both_sources_fail_marks_degraded(self, monkeypatch):
        monkeypatch.setattr(mi, "_yfinance_get", lambda *a, **k: None)
        monkeypatch.setattr(mi, "_sina_foreign_get", lambda symbol: None)
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

        assert "macro.gold_usd_oz" in data["data_quality"]["degraded_fields"]
        assert "macro.wti_oil_usd" in data["data_quality"]["degraded_fields"]
        assert data["macro"]["gold_usd_oz"] is None
        assert data["macro"]["gold_usd_oz_source"] is None
