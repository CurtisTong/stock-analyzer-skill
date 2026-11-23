"""P1-8 回归测试（2026-11-21 review §3.1 #8）：东财 "-" 变 0 价行情。"""

from __future__ import annotations

import json

import pytest

from common.exceptions import ParseError
from fetchers.quote.eastmoney_quote import EastmoneyQuoteFetcher


def _mock_raw(monkeypatch, payload):
    monkeypatch.setattr(
        "fetchers.quote.eastmoney_quote.http_get",
        lambda *a, **k: json.dumps(payload).encode("utf-8"),
    )


@pytest.mark.parametrize("bad_price", ["-", None, "", 0, "abc"])
def test_invalid_core_price_returns_none(monkeypatch, bad_price):
    """核心字段 price 无效时 fetcher 必须失败，让 manager 切源（P1-8）。"""
    _mock_raw(
        monkeypatch,
        {"rc": 0, "data": {"f43": bad_price, "f57": "600989", "f58": "宝丰能源"}},
    )
    assert EastmoneyQuoteFetcher().fetch("sh600989") is None


def test_valid_price_still_parsed(monkeypatch):
    _mock_raw(
        monkeypatch,
        {"rc": 0, "data": {"f43": 1050, "f57": "600989", "f58": "宝丰能源", "f60": 1000}},
    )
    rec = EastmoneyQuoteFetcher().fetch("sh600989")
    assert rec is not None
    assert rec["price"] == "10.5"
    assert rec["prev_close"] == "10.0"
    assert rec["source"] == "eastmoney"


def test_malformed_json_still_raises_parse_error(monkeypatch):
    monkeypatch.setattr(
        "fetchers.quote.eastmoney_quote.http_get",
        lambda *a, **k: b"<html>anti-bot</html>",
    )
    with pytest.raises(ParseError):
        EastmoneyQuoteFetcher().fetch("sh600989")
