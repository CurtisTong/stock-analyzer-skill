"""腾讯行情的美股指数路由单测。

背景：`quote.py us:^gspc` 之前只走 yfinance / 雪球，两源 429/400 时美股三大指数
整段不可用（2026-11-20 实测返回 `[]`）。腾讯 `qt.gtimg.cn/q=usINX` 有源可用，
缺的只是 `^GSPC → usINX` 这层映射。
"""

from __future__ import annotations

import pytest

from fetchers.quote.tencent_quote import _US_INDEX_SYMBOLS, TencentQuoteFetcher


def _tencent_line(symbol: str, name: str, price: str, prev: str, pct: str) -> str:
    """拼一行腾讯行情（`parse_tencent_line` 要求至少 50 段）。"""
    parts = ["0"] * 60
    parts[1] = name
    parts[2] = f".{symbol}"
    parts[3] = price
    parts[4] = prev
    parts[32] = pct
    return f'v_us{symbol}="{"~".join(parts)}";'


@pytest.mark.parametrize(
    ("code", "symbol"),
    [
        ("us:^gspc", "usINX"),
        ("us:^spx", "usINX"),
        ("us:^ixic", "usIXIC"),
        ("us:^dji", "usDJI"),
        ("US:^DJI", "usDJI"),  # 大小写无关
    ],
)
def test_symbol_mapping(code, symbol):
    assert _US_INDEX_SYMBOLS[code.lower()] == symbol


@pytest.mark.parametrize(
    ("code", "symbol", "name", "price"),
    [
        ("us:^gspc", "INX", "标普500", "7175.83"),
        ("us:^ixic", "IXIC", "纳斯达克", "23879.20"),
        ("us:^dji", "DJI", "道琼斯", "49097.06"),
    ],
)
def test_fetch_us_index(monkeypatch, code, symbol, name, price):
    fetcher = TencentQuoteFetcher()
    line = _tencent_line(symbol, name, price, "7323.63", "-2.02")
    monkeypatch.setattr(
        "fetchers.quote.tencent_quote.http_get", lambda *a, **k: line.encode("gbk")
    )

    rec = fetcher.fetch(code)

    assert rec is not None
    assert rec["name"] == name
    assert rec["price"] == price
    assert rec["source"] == "tencent"
    # 返回时保留调用方传入的代码，避免下游按 .INX 对不上
    assert rec["code"] == code.lower()


def test_fetch_us_index_empty_response(monkeypatch):
    fetcher = TencentQuoteFetcher()
    monkeypatch.setattr(
        "fetchers.quote.tencent_quote.http_get", lambda *a, **k: b""
    )
    assert fetcher.fetch("us:^gspc") is None


def test_non_index_us_code_still_goes_generic_path(monkeypatch):
    """`us:spy` 这类非指数标的不在本映射里，不应被误接。"""
    seen = {}

    def _fake_get(url, **kwargs):
        seen["url"] = url
        return b""

    fetcher = TencentQuoteFetcher()
    monkeypatch.setattr("fetchers.quote.tencent_quote.http_get", _fake_get)

    assert fetcher.fetch("us:spy") is None
    assert "us:spy" in seen["url"]
