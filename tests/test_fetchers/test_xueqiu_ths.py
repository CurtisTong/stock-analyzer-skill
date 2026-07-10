"""雪球 + 同花顺数据源测试。"""

import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from fetchers.quote.xueqiu_quote import (
    XueqiuQuoteFetcher,
    _to_xueqiu_symbol,
    _parse_quote,
)
from fetchers.quote.ths_quote import (
    ThsQuoteFetcher,
    _to_ths_params,
    _parse_quote as _ths_parse_quote,
)
from common.exceptions import NetworkError

# ═══════════════════════════════════════════════════════════════
# xueqiu_quote
# ═══════════════════════════════════════════════════════════════


class TestXueqiuQuoteFetcher:
    """XueqiuQuoteFetcher 测试。"""

    def setup_method(self):
        self.fetcher = XueqiuQuoteFetcher()

    def test_name_and_priority(self):
        assert self.fetcher.name == "xueqiu_quote"
        assert self.fetcher.priority == 8

    def test_to_xueqiu_symbol_with_prefix(self):
        assert _to_xueqiu_symbol("SH600519") == "SH600519"
        assert _to_xueqiu_symbol("sz000858") == "SZ000858"

    def test_to_xueqiu_symbol_without_prefix(self):
        assert _to_xueqiu_symbol("600519") == "SH600519"
        assert _to_xueqiu_symbol("000858") == "SZ000858"

    def test_parse_quote_normal(self):
        data = {
            "data": {
                "quote": {
                    "symbol": "SH600519",
                    "name": "贵州茅台",
                    "current": 1800.00,
                    "open": 1795.00,
                    "high": 1810.00,
                    "low": 1790.00,
                    "last_close": 1790.00,
                    "volume": 1234500,
                    "amount": 2234567000.00,
                    "turnover_rate": 0.15,
                    "pe_ttm": 25.60,
                    "pb": 8.20,
                    "market_capital": 2260000000000,
                }
            }
        }
        result = _parse_quote(data)
        assert result is not None
        assert result["name"] == "贵州茅台"
        assert result["source"] == "xueqiu"
        # 验证字段名与 _dict_to_quote 兼容（标准化字段名）
        assert "prev_close" in result  # 非 "pre_close"
        assert "turnover" in result  # 非 "turnover_rate"
        assert "total_cap" in result  # 非 "market_cap"
        assert result["prev_close"] == 1790.00
        assert result["turnover"] == 0.15
        # total_cap 应为亿元（market_cap / 1e8）
        assert result["total_cap"] == 22600.0

    def test_parse_quote_no_data(self):
        assert _parse_quote({}) is None
        assert _parse_quote({"data": {}}) is None
        assert _parse_quote(None) is None

    def test_fetch_normal(self):
        data = {
            "data": {
                "quote": {
                    "symbol": "SH600519",
                    "name": "贵州茅台",
                    "current": 1800.00,
                    "open": 1795.00,
                    "high": 1810.00,
                    "low": 1790.00,
                    "last_close": 1790.00,
                    "volume": 1234500,
                    "amount": 2234567000.00,
                    "turnover_rate": 0.15,
                    "pe_ttm": 25.60,
                    "pb": 8.20,
                    "market_capital": 2260000000000,
                }
            }
        }
        with patch(
            "fetchers.quote.xueqiu_quote.http_get_with_headers",
            return_value=json.dumps(data).encode(),
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert result["name"] == "贵州茅台"

    def test_fetch_empty_response(self):
        with patch(
            "fetchers.quote.xueqiu_quote.http_get_with_headers", return_value=b"{}"
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_http_error(self):
        """HTTP 错误：返回 None（xueqiu 内部 catch）。"""
        with patch(
            "fetchers.quote.xueqiu_quote.http_get_with_headers",
            side_effect=NetworkError("url", "err", 3),
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_invalid_json(self):
        with patch(
            "fetchers.quote.xueqiu_quote.http_get_with_headers", return_value=b"bad"
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# ths_quote
# ═══════════════════════════════════════════════════════════════


class TestThsQuoteFetcher:
    """ThsQuoteFetcher 测试。"""

    def setup_method(self):
        self.fetcher = ThsQuoteFetcher()

    def test_name_and_priority(self):
        assert self.fetcher.name == "ths_quote"
        assert self.fetcher.priority == 3

    def test_to_ths_params_sh(self):
        assert _to_ths_params("SH600519") == ("1", "600519")
        assert _to_ths_params("sh600519") == ("1", "600519")

    def test_to_ths_params_sz(self):
        assert _to_ths_params("SZ000858") == ("0", "000858")

    def test_to_ths_params_plain(self):
        assert _to_ths_params("600519") == ("1", "600519")
        assert _to_ths_params("000858") == ("0", "000858")

    def test_parse_quote_normal(self):
        text = '{"data":"2025-06-10,1790.00,1810.00,1785.00,1800.00,12345;2025-06-11,1800.00,1815.00,1795.00,1805.00,11000"}'
        result = _ths_parse_quote(text, "600519")
        assert result is not None
        assert result["code"] == "600519"
        assert result["source"] == "ths"
        # 最后一条数据
        assert result["price"] == 1805.0

    def test_parse_quote_no_braces(self):
        result = _ths_parse_quote("no json here", "600519")
        assert result is None

    def test_parse_quote_empty_data(self):
        text = '{"data":""}'
        result = _ths_parse_quote(text, "600519")
        assert result is None

    def test_fetch_normal(self):
        raw = b'{"data":"2025-06-10,1790.00,1810.00,1785.00,1800.00,12345;2025-06-11,1800.00,1815.00,1795.00,1805.00,11000"}'
        with patch("fetchers.quote.ths_quote.http_get", return_value=raw):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert result["source"] == "ths"

    def test_fetch_empty_response(self):
        with patch("fetchers.quote.ths_quote.http_get", return_value=b""):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_http_error(self):
        """HTTP 错误：返回 None（ths 内部 catch）。"""
        with patch(
            "fetchers.quote.ths_quote.http_get",
            side_effect=NetworkError("url", "err", 3),
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_short_fields(self):
        """数据字段不足 5 个：返回 None。"""
        raw = b'{"data":"2025-06-10,1790.00"}'
        with patch("fetchers.quote.ths_quote.http_get", return_value=raw):
            result = self.fetcher.fetch("sh600519")
        assert result is None
