"""P1-12 回归测试（2026-11-21 review §3.1 #12）：雪球 symbol 转换。"""

from __future__ import annotations

import json

import pytest

from common import NOT_HANDLED
from fetchers.quote.xueqiu_quote import XueqiuQuoteFetcher, _parse_quote, _to_xueqiu_symbol


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("600989.SH", "SH600989"),
        ("000001.sz", "SZ000001"),
        ("600989", "SH600989"),
        ("sh600989", "SH600989"),
        ("SZ300750", "SZ300750"),
        ("430047.BJ", "BJ430047"),
    ],
)
def test_suffix_symbols_converted(code, expected):
    assert _to_xueqiu_symbol(code) == expected


@pytest.mark.parametrize("code", ["us:aapl", "us:^gspc", "hk:00700"])
def test_cross_market_returns_not_handled(code):
    assert _to_xueqiu_symbol(code) is NOT_HANDLED
    assert XueqiuQuoteFetcher().fetch(code) is NOT_HANDLED


def test_parse_quote_validates_returned_code():
    payload = {"data": {"quote": {"symbol": "SH600989", "current": "10.5"}}}
    rec = _parse_quote(payload, expected_symbol="SH600989")
    assert rec is not None
    assert rec["code"] == "SH600989"
    assert rec["price"] == 10.5
    assert _parse_quote(payload, expected_symbol="SZ000001") is None, "返回 code 不符必须拒绝"


def test_fetch_validates_returned_code(monkeypatch):
    responses = iter(
        [
            {"data": {"quote": {"symbol": "SH600989", "current": "10.5"}}},
            {"data": {"quote": {"symbol": "SZ000001", "current": "9.9"}}},
        ]
    )
    monkeypatch.setattr(
        "fetchers.quote.xueqiu_quote.http_get_with_headers",
        lambda *a, **k: json.dumps(next(responses)).encode("utf-8"),
    )
    fetcher = XueqiuQuoteFetcher()
    rec = fetcher.fetch("600989.SH")
    assert rec is not None
    assert rec["code"] == "SH600989"
    assert fetcher.fetch("600989.SH") is None, "雪球返回错标的时不得当成功（P1-12）"
