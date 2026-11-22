"""macro_indicators 新鲜度接入单测（monkeypatch，不连网、不写运行时 snapshot）。

用 2026-11-22 20:48 抓到的真实报文形状做 fixture：
CBOE 顶层 timestamp 是报文生成时间，data.last_trade_time 才是报价时间；
腾讯 usVIX 现价 21.67 的报文自带日期是 2026-09-11（72 天前）。
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone

import macro_indicators as mi
from common import freshness

NOW_UTC = datetime(2026, 11, 22, 12, 49, tzinfo=timezone.utc)  # 北京 20:49
WEEKEND_CHECK_UTC = datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc)  # 周一 08:30 北京
FRESH_UTC = datetime(2026, 11, 20, 21, 30, tzinfo=timezone.utc)
QUOTE_TS = "2026-11-20T16:15:01"
STALE_TENCENT_TS = "2026-09-11 09:30:00"

CBOE_RAW = {
    "timestamp": "2026-11-22 12:48:32",  # 报文生成时间（UTC），禁止当 as_of
    "data": {
        "symbol": "^VIX",
        "current_price": 35.89,
        "price_change_percent": 20.7579,
        "close": 35.89,
        "prev_day_close": 35.89,  # 不可靠：反推昨收应≈29.72
        "last_trade_time": QUOTE_TS,
    },
    "symbol": "_VIX",
}


class _Resp:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw


class TestCboeQuoteTime:
    def test_uses_last_trade_time_with_cboe_referer(self, monkeypatch):
        seen = {}

        def fake_urlopen(req, timeout=None):
            seen["url"] = req.full_url
            seen["referer"] = req.get_header("Referer")
            return _Resp(CBOE_RAW)

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        # CBOE_RAW 是真实脏报文（current==prev 却报 +20.76%），dirty=True 必须被带回
        assert mi._cboe_vix() == (35.89, QUOTE_TS, True)
        assert seen["url"] == mi._CBOE_VIX_URL
        assert seen["referer"] == "https://www.cboe.com/"

    def test_missing_last_trade_time_returns_none_not_message_time(self, monkeypatch):
        payload = {"timestamp": "2026-11-22 12:48:32", "data": {"current_price": 35.89}}
        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _Resp(payload))
        # 有值但没有报价时间 → 不可用；绝不拿顶层 timestamp 顶替
        assert mi._cboe_vix() is None


class TestCboeDirtyGuard:
    def test_real_dirty_payload_is_flagged(self):
        # 2026-11-22 20:48 真实报文：current==prev==35.89 却报 +20.7579%
        assert mi._cboe_payload_is_dirty(CBOE_RAW["data"]) is True

    def test_clean_payload_not_flagged(self):
        clean = dict(CBOE_RAW["data"], prev_day_close=29.72)
        assert mi._cboe_payload_is_dirty(clean) is False

    def test_missing_field_not_flagged(self):
        # 缺字段走「缺字段→不可用」路径，不判脏（避免误伤）
        assert mi._cboe_payload_is_dirty({"current_price": 35.89}) is False

    def test_fetch_vix_discards_dirty_field_and_marks_dirty(self, monkeypatch):
        # 端到端：脏报文进来，值整字段丢弃（None），带 dirty 标记，不降级到腾讯旧值
        self_isolate = TestFetchVixFreshness._isolate
        self_isolate(monkeypatch)
        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _Resp(CBOE_RAW))
        monkeypatch.setattr(mi, "_yfinance_get", lambda symbol: None)
        monkeypatch.setattr(
            mi,
            "_tencent_us_index_get_with_ts",
            lambda symbol: (_ for _ in ()).throw(AssertionError("脏数据不得降级到腾讯")),
        )
        out = mi.fetch_vix()
        assert out is not None and out["dirty"] is True
        assert out["value"] is None
        assert out["quote_time_local"] == QUOTE_TS
        assert "current_price==prev_day_close" in out["dirty_reason"]

    def test_fetch_all_reports_vix_dirty_and_unavailable(self, monkeypatch):
        fetchers = [
            "fetch_treasury_10y", "fetch_usd_index", "fetch_usd_cny", "fetch_gold",
            "fetch_brent_oil", "fetch_wti_oil", "fetch_lithium", "fetch_margin_total",
            "fetch_if_basis", "fetch_ic_basis", "fetch_ih_basis", "fetch_erp_sh300",
        ]
        for name in fetchers:
            monkeypatch.setattr(mi, name, lambda: None)
        monkeypatch.setattr(mi, "fetch_vix", lambda: {
            "value": None, "dirty": True, "source": "cboe_delayed", "symbol": "^VIX",
            "dirty_reason": "current_price==prev_day_close 但 price_change_percent!=0",
        })
        out = mi.fetch_all()
        degraded = out["data_quality"]["degraded_fields"]
        assert "macro.vix_dirty" in degraded
        assert "macro.vix" in degraded  # 值已丢弃，不可用


class TestFetchVixFreshness:
    @staticmethod
    def _isolate(monkeypatch):
        monkeypatch.setattr(mi, "_load_snapshot", lambda: {})
        monkeypatch.setattr(mi, "_save_snapshot", lambda *a, **k: None)
        monkeypatch.setattr(mi, "_yfinance_get", lambda symbol: None)
        monkeypatch.setattr(freshness, "_utcnow", lambda: NOW_UTC)

    def test_cboe_as_of_is_quote_time_and_weekend_is_marked_stale(self, monkeypatch):
        self._isolate(monkeypatch)
        monkeypatch.setattr(freshness, "_utcnow", lambda: WEEKEND_CHECK_UTC)
        monkeypatch.setattr(mi, "_cboe_vix", lambda: (35.89, QUOTE_TS, False))
        out = mi.fetch_vix()
        assert out["value"] == 35.89
        assert out["source"] == "cboe_delayed"
        # 报价时间 2026-11-20 16:15 ET = 北京 2026-11-21 05:15，不是抓取日 11-22
        assert out["as_of"] == "2026-11-21T05:15:01+08:00"
        assert out["quote_time_field"] == "last_trade_time"
        assert out["stale"] is True
        assert "数据年龄" in out["stale_reason"]

    def test_fresh_cboe_quote_not_marked_stale(self, monkeypatch):
        self._isolate(monkeypatch)
        monkeypatch.setattr(freshness, "_utcnow", lambda: FRESH_UTC)
        monkeypatch.setattr(mi, "_cboe_vix", lambda: (35.89, QUOTE_TS, False))
        out = mi.fetch_vix()
        assert out["as_of"] == "2026-11-21T05:15:01+08:00"
        assert "stale" not in out

    def test_rejects_72_day_old_tencent_value(self, monkeypatch):
        self._isolate(monkeypatch)
        monkeypatch.setattr(mi, "_cboe_vix", lambda: None)
        monkeypatch.setattr(mi, "_tencent_us_index_get_with_ts", lambda symbol: (21.67, STALE_TENCENT_TS))
        # 坏数据证明：旧实现会返回 21.67 并盖当天 as_of；新实现必须拒绝
        assert mi.fetch_vix() is None

    def test_accepts_fresh_tencent_with_quote_time(self, monkeypatch):
        self._isolate(monkeypatch)
        monkeypatch.setattr(freshness, "_utcnow", lambda: FRESH_UTC)
        monkeypatch.setattr(mi, "_cboe_vix", lambda: None)
        monkeypatch.setattr(mi, "_tencent_us_index_get_with_ts", lambda symbol: (21.67, QUOTE_TS))
        out = mi.fetch_vix()
        assert out["source"] == "tencent_us_index"
        assert out["as_of"] == "2026-11-21T05:15:01+08:00"
        assert "stale" not in out


def test_fetch_all_reports_stale_as_degraded(monkeypatch):
    fetchers = [
        "fetch_treasury_10y",
        "fetch_usd_index",
        "fetch_usd_cny",
        "fetch_gold",
        "fetch_brent_oil",
        "fetch_wti_oil",
        "fetch_lithium",
        "fetch_margin_total",
        "fetch_if_basis",
        "fetch_ic_basis",
        "fetch_ih_basis",
        "fetch_erp_sh300",
    ]
    for name in fetchers:
        monkeypatch.setattr(mi, name, lambda: None)
    monkeypatch.setattr(
        mi,
        "fetch_vix",
        lambda: {
            "value": 35.89,
            "as_of": "2026-11-21T05:15:01+08:00",
            "source": "cboe_delayed",
            "stale": True,
        },
    )
    out = mi.fetch_all()
    degraded = out["data_quality"]["degraded_fields"]
    assert "macro.vix_stale" in degraded
    assert "macro.vix" not in degraded
