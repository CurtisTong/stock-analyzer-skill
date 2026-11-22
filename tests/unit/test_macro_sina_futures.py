"""铝价/氧化铝价差数据层（feat/macro-aluminum-spread）。

数据源：新浪国内商品期货，零依赖 stdlib。
- 实时 hq.sinajs.cn 用 nf_ 前缀（nf_AL0 / nf_AO0）
- 历史 getDailyKLine 用无前缀（AL0 / AO0）
- 价差 L2 = AL - 1.92 * AO

全部 monkeypatch，不连网。
"""

from __future__ import annotations

import io
import json

import pytest

import macro_indicators as mi


# ═══════════════════════════════════════════════════════════════
# Mock HTTP 响应
# ═══════════════════════════════════════════════════════════════


def _rt_payload(code: str, name: str, price: float, settle: float, date: str) -> str:
    """构造新浪 nf_ 实时快照（字段 8=最新价, 10=昨结算, 17=日期）。"""
    parts = [name, "010000", "21410.000", "21755.000", "21390.000", "0.000",
             "21585.000", "21600.000", f"{price:.3f}", "0.000", f"{settle:.3f}",
             "2", "3", "258936.000", "146610", "沪", name, date, "1"]
    return f'var hq_str_{code}="{",".join(parts)}";'


_AL_RT = _rt_payload("nf_AL0", "铝连续", 21585.0, 21425.0, "2026-11-21")
_AO_RT = _rt_payload("nf_AO0", "氧化铝连续", 2609.0, 2619.0, "2026-11-21")


def _hist_payload(sym: str, closes: list[float]) -> str:
    rows = [{"d": f"2026-11-{i+1:02d}", "o": str(c), "h": str(c),
             "l": str(c), "c": str(c), "v": "100", "p": "100", "s": str(c)}
            for i, c in enumerate(closes)]
    return "/*<script>location.href='//sina.com';</script>*/\nvar _%s=(%s);" % (sym, json.dumps(rows))


_AL_HIST = [21000.0 + i * 10 for i in range(250)]  # 21000..22490
_AO_HIST = [2700.0 - i for i in range(250)]        # 2700..2451


class _Resp(io.BytesIO):
    pass


def _mock_urlopen(req, **kwargs):
    """按 URL 返回真实格式的响应（实时 gbk / 历史 utf-8 JSONP）。

    生产代码传入 urllib.request.Request 对象，需取 full_url。
    """
    url = getattr(req, "full_url", str(req))
    if "hq.sinajs.cn" in url:
        if "nf_AL0" in url and "nf_AO0" in url:
            body = _AL_RT + "\n" + _AO_RT
        elif "nf_AO0" in url:
            body = _AO_RT
        else:
            body = _AL_RT
        return _Resp(body.encode("gbk"))
    if "getDailyKLine" in url:
        sym = "AL0" if "symbol=AL0" in url else "AO0"
        body = _hist_payload(sym, _AL_HIST if sym == "AL0" else _AO_HIST)
        return _Resp(body.encode("utf-8"))
    raise AssertionError(f"未预期的 URL: {url}")


@pytest.fixture(autouse=True)
def _isolated_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(mi, "SNAPSHOT_PATH", tmp_path / "macro_snapshot.json")
    monkeypatch.setattr(mi, "_load_snapshot", lambda: {})
    monkeypatch.setattr(mi, "_save_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(mi, "_key_is_fresh", lambda *a, **k: False)


# ═══════════════════════════════════════════════════════════════
# 实时快照解析
# ═══════════════════════════════════════════════════════════════


class TestSinaFuturesRealtime:
    def test_parses_price_settle_date(self, monkeypatch):
        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp(_AL_RT.encode("gbk")))
        out = mi._sina_futures_realtime("nf_AL0", 8, 10, 17)
        assert out == {"price": 21585.0, "settle": 21425.0, "date": "2026-11-21"}

    def test_network_error_returns_none(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("blocked")

        monkeypatch.setattr("urllib.request.urlopen", boom)
        assert mi._sina_futures_realtime("nf_AL0", 8, 10, 17) is None

    def test_empty_quote_returns_none(self, monkeypatch):
        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp(b'var hq_str_nf_AO0="";'))
        assert mi._sina_futures_realtime("nf_AO0", 8, 10, 17) is None

    def test_realtime_codes_must_use_nf_prefix(self):
        """防致命坑：实时用裸 AL0 会拿到 2024 过期数据。"""
        assert mi._SINA_FUTURES_REALTIME["aluminum"][0] == "nf_AL0"
        assert mi._SINA_FUTURES_REALTIME["alumina"][0] == "nf_AO0"

    def test_history_codes_must_not_use_nf_prefix(self):
        """防致命坑：历史用 nf_AL0 无数据。"""
        assert mi._SINA_FUTURES_HISTORY == {"aluminum": "AL0", "alumina": "AO0"}


# ═══════════════════════════════════════════════════════════════
# 历史 JSONP 解析
# ═══════════════════════════════════════════════════════════════


class TestSinaFuturesHistory:
    def test_parses_jsonp_and_returns_close_series(self, monkeypatch):
        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp(_hist_payload("AL0", _AL_HIST).encode()))
        out = mi._sina_futures_history("AL0")
        assert out == _AL_HIST

    def test_respects_lookback(self, monkeypatch):
        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp(_hist_payload("AL0", _AL_HIST).encode()))
        assert mi._sina_futures_history("AL0", lookback=10) == _AL_HIST[-10:]

    def test_network_error_returns_none(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("blocked")

        monkeypatch.setattr("urllib.request.urlopen", boom)
        assert mi._sina_futures_history("AL0") is None


# ═══════════════════════════════════════════════════════════════
# 三段式 fetch_commodity_sina
# ═══════════════════════════════════════════════════════════════


class TestFetchCommoditySina:
    def test_realtime_success_returns_price_and_percentile(self, monkeypatch):
        monkeypatch.setattr("urllib.request.urlopen", _mock_urlopen)
        out = mi.fetch_aluminum_sina()
        assert out["value"] == 21585.0
        assert out["source"] == "sina_futures"
        assert out["symbol"] == "nf_AL0"
        assert isinstance(out["percentile"], float)
        assert out["history"] == _AL_HIST

    def test_fresh_fixture_short_circuits(self, monkeypatch):
        snapshot = {"aluminum_cny_t": 9999.0, "aluminum_percentile_1y": 55.5, "updated": "2026-11-22T09:00:00"}

        def boom(*a, **k):
            raise AssertionError("新鲜 fixture 不应发起网络请求")

        monkeypatch.setattr(mi, "_load_snapshot", lambda: snapshot)
        monkeypatch.setattr(mi, "_key_is_fresh", lambda s, k: True)
        monkeypatch.setattr("urllib.request.urlopen", boom)
        out = mi.fetch_aluminum_sina()
        assert out["value"] == 9999.0
        assert out["source"] == "fixture"
        assert out["percentile"] == 55.5

    def test_stale_fixture_fallback(self, monkeypatch):
        monkeypatch.setattr(mi, "_load_snapshot", lambda: {"aluminum_cny_t": 20000.0, "updated": "2026-01-01T00:00:00"})

        def boom(*a, **k):
            raise OSError("blocked")

        monkeypatch.setattr("urllib.request.urlopen", boom)
        out = mi.fetch_aluminum_sina()
        assert out["value"] == 20000.0
        assert out["source"] == "fixture(stale)"

    def test_all_fail_returns_none(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("blocked")

        monkeypatch.setattr("urllib.request.urlopen", boom)
        assert mi.fetch_alumina() is None


# ═══════════════════════════════════════════════════════════════
# 价差计算
# ═══════════════════════════════════════════════════════════════


class TestAluminaSpread:
    def test_l2_formula(self, monkeypatch):
        monkeypatch.setattr("urllib.request.urlopen", _mock_urlopen)
        out = mi.fetch_aluminum_alumina_spread()
        expected = 21585.0 - 1.92 * 2609.0
        assert out["value"] == round(expected, 2)
        assert out["value"] == 16575.72
        assert out["ratio"] == 1.92
        assert out["source"] == "sina_futures(derived)"
        assert "L2" in out["note"]

    def test_accepts_prefetched_inputs(self):
        al = {"value": 22000.0, "as_of": "x", "history": [22000.0] * 250}
        ao = {"value": 2500.0, "as_of": "x", "history": [2500.0] * 250}
        out = mi.fetch_aluminum_alumina_spread(al, ao)
        assert out["value"] == round(22000.0 - 1.92 * 2500.0, 2)
        assert isinstance(out["percentile"], float)

    def test_missing_input_returns_none(self, monkeypatch):
        # 显式 None 表示"未传入，需自行拉取"；此处让两个拉取都失败
        monkeypatch.setattr(mi, "fetch_aluminum_sina", lambda: None)
        monkeypatch.setattr(mi, "fetch_alumina", lambda: None)
        assert mi.fetch_aluminum_alumina_spread() is None

    def test_no_history_still_returns_value_without_percentile(self):
        al = {"value": 21585.0, "as_of": "x"}
        ao = {"value": 2609.0, "as_of": "x"}
        out = mi.fetch_aluminum_alumina_spread(al, ao)
        assert out["value"] == 16575.72
        assert out["percentile"] is None

    def test_fresh_fixture_short_circuits(self, monkeypatch):
        """断网时从 fixture 恢复价差与分位。"""
        snapshot = {
            "al_alumina_spread_cny_t": 16000.0,
            "al_alumina_spread_percentile_1y": 8.8,
            "al_alumina_spread_ratio": 1.92,
            "updated": "2026-11-22T09:00:00",
        }

        def boom(*a, **k):
            raise AssertionError("新鲜 fixture 不应发起网络请求")

        monkeypatch.setattr(mi, "_load_snapshot", lambda: snapshot)
        monkeypatch.setattr(mi, "_key_is_fresh", lambda s, k: True)
        monkeypatch.setattr("urllib.request.urlopen", boom)
        out = mi.fetch_aluminum_alumina_spread()
        assert out["value"] == 16000.0
        assert out["source"] == "fixture"
        assert out["percentile"] == 8.8


# ═══════════════════════════════════════════════════════════════
# fetch_all 输出契约
# ═══════════════════════════════════════════════════════════════


class TestFetchAllContract:
    def test_new_fields_present_and_no_history(self, monkeypatch):
        monkeypatch.setattr("urllib.request.urlopen", _mock_urlopen)
        for name in (
            "fetch_treasury_10y", "fetch_usd_index", "fetch_usd_cny", "fetch_vix",
            "fetch_gold", "fetch_brent_oil", "fetch_wti_oil", "fetch_lithium",
            "fetch_margin_total", "fetch_if_basis", "fetch_ic_basis",
            "fetch_ih_basis", "fetch_erp_sh300",
        ):
            monkeypatch.setattr(mi, name, lambda *a, **k: None, raising=False)

        data = mi.fetch_all()
        m = data["macro"]
        assert m["aluminum_cny_t"] == 21585.0
        assert m["alumina_cny_t"] == 2609.0
        assert m["al_alumina_spread_cny_t"] == 16575.72
        assert m["al_alumina_spread_ratio"] == 1.92
        assert m["aluminum_cny_t_source"] == "sina_futures"
        assert m["al_alumina_spread_cny_t_source"] == "sina_futures(derived)"
        assert "history" not in data["_raw"]["macro"]["aluminum_cny_t"]

    def test_failed_fetches_mark_degraded(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("blocked")

        monkeypatch.setattr("urllib.request.urlopen", boom)
        for name in (
            "fetch_treasury_10y", "fetch_usd_index", "fetch_usd_cny", "fetch_vix",
            "fetch_gold", "fetch_brent_oil", "fetch_wti_oil", "fetch_lithium",
            "fetch_margin_total", "fetch_if_basis", "fetch_ic_basis",
            "fetch_ih_basis", "fetch_erp_sh300",
        ):
            monkeypatch.setattr(mi, name, lambda *a, **k: None, raising=False)

        data = mi.fetch_all()
        degraded = data["data_quality"]["degraded_fields"]
        assert "macro.aluminum_cny_t" in degraded
        assert "macro.alumina_cny_t" in degraded
        assert "macro.al_alumina_spread" in degraded
        assert data["macro"]["aluminum_cny_t"] is None
