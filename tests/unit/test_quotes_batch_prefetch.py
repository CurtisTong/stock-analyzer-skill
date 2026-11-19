"""全市场批量行情预取（P1：screener 5000+ 只逐只请求 15 分钟无产出）。

腾讯单请求支持多代码：60 只/批把 5382 只的请求数从 5382 次压到 ~90 次
（实测 10.2s 取全 5382 只）。本文件锁死：
1. fetch_many 能解析多代码响应、过滤未请求的代码、单批失败不抛；
2. get_quotes 在数量 ≥ 阈值时走批量，缺失代码回退逐只；
3. 数量小于阈值时行为不变（仍走逐只并行，缓存命中友好）。

全部 monkeypatch，不连网。
"""

from __future__ import annotations

import pytest

import data as data_pkg
from data import get_quotes
from fetchers.quote import tencent_quote as tq

# 真实响应片段（2026-11-19 抓取，GBK 解码后）：两只代码、以 ";" 分隔
_FAKE_BODY = (
    'v_sh600519="1~贵州茅台~600519~1460.21~1442.66~1442.00~42692~23549~19143~1460.21~4~'
    '1460.19~1~1460.11~2~1460.10~5~1460.09~1~1460.25~2~1460.48~1~1460.56~3~1460.58~1~'
    '1460.59~3~~20261119161455~17.55~1.22~1464.99~1432.10~1460.21/42692/6192213063~42692~'
    '619221~0.34~22.22~~1464.99~1432.10~2.28~18253.82~18253.82~6.73~1586.93~1298.39~1.19~'
    '3~1450.45~21.24~22.17~~~-0.05~619221.3063~204.4294~14~   A~GP-A~8.23~3.54~";'
    'v_sz000001="1~平安银行~000001~12.34~12.20~12.21~100~50~50~12.34~1~12.33~1~12.32~1~'
    '12.31~1~12.30~1~12.35~1~12.36~1~12.37~1~12.38~1~12.39~1~~20261119161455~0.14~1.15~'
    '12.50~12.10~12.34/100/123400~100~12340~0.34~5.5~~12.50~12.10~3.28~1000.0~1000.0~'
    '0.5~13.42~10.98~1.1~1~12.30~1.2~1.1~~~0.01~1234~20.1~1~   A~GP-A~2.1~1.2~";'
)


class TestFetchMany:
    def test_parses_all_requested_codes(self, monkeypatch):
        monkeypatch.setattr(tq, "http_get", lambda *a, **k: _FAKE_BODY.encode("gbk"))
        monkeypatch.setattr(tq, "decode_gbk", lambda raw: raw.decode("gbk"))
        out = tq.TencentQuoteFetcher().fetch_many(["sh600519", "sz000001"])
        assert set(out) == {"600519", "000001"}
        assert out["600519"]["name"] == "贵州茅台"
        assert out["600519"]["source"] == "tencent"

    def test_filters_codes_not_requested(self, monkeypatch):
        monkeypatch.setattr(tq, "http_get", lambda *a, **k: _FAKE_BODY.encode("gbk"))
        monkeypatch.setattr(tq, "decode_gbk", lambda raw: raw.decode("gbk"))
        out = tq.TencentQuoteFetcher().fetch_many(["sh600519"])
        assert set(out) == {"600519"}

    def test_batch_failure_does_not_raise(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("network down")

        monkeypatch.setattr(tq, "http_get", boom)
        assert tq.TencentQuoteFetcher().fetch_many(["sh600519", "sz000001"]) == {}

    def test_multiple_batches(self, monkeypatch):
        calls = []

        def fake_http(url, **k):
            calls.append(url)
            code = url.rsplit("=", 1)[-1]
            c6 = code[2:]
            body = f'v_{code}="1~样本{c6}~{c6}~10.0~9.9~9.9~1~1~1~'
            return (body + '~"~' * 0 + '";').encode("gbk")

        monkeypatch.setattr(tq, "http_get", fake_http)
        monkeypatch.setattr(tq, "decode_gbk", lambda raw: raw.decode("gbk"))
        codes = [f"sh60{i:04d}" for i in range(5)]
        out = tq.TencentQuoteFetcher().fetch_many(codes, batch_size=2)
        assert len(calls) == 3  # 5 只 / 2 只一批
        assert isinstance(out, dict)


class TestGetQuotesRouting:
    def test_small_batch_uses_parallel_path(self, monkeypatch):
        called = []
        monkeypatch.setattr("common.parallel_map", lambda fn, items, timeout=30: called.append(items) or {})
        monkeypatch.setattr(data_pkg, "_get_quotes_tencent_batch", lambda codes: pytest.fail("小数量不应走批量"))
        get_quotes(["sh600519", "sz000001"], use_cache=False)
        assert called and len(called[0]) == 2

    def test_large_batch_uses_tencent_batch(self, monkeypatch):
        codes = [f"sh60{i:04d}" for i in range(250)]
        seen = {}

        class _FakeQuote:
            def __init__(self, code):
                self.code = code

        def fake_batch(normalized):
            seen["called"] = True
            return {c: _FakeQuote(c) for c in normalized}

        monkeypatch.setattr(data_pkg, "_get_quotes_tencent_batch", fake_batch)
        monkeypatch.setattr("common.parallel_map", lambda *a, **k: {})
        out = get_quotes(codes, use_cache=False)
        assert seen.get("called") is True
        assert len(out) == 250

    def test_missing_codes_fall_back_to_per_code(self, monkeypatch):
        codes = [f"sh60{i:04d}" for i in range(210)]
        fallback_calls = []

        class _FakeQuote:
            def __init__(self, code):
                self.code = code

        monkeypatch.setattr(data_pkg, "_get_quotes_tencent_batch", lambda normalized: {})
        monkeypatch.setattr(
            "common.parallel_map",
            lambda fn, items, timeout=30: fallback_calls.append(list(items)) or {},
        )
        get_quotes(codes, use_cache=False)
        assert fallback_calls and len(fallback_calls[0]) == 210
