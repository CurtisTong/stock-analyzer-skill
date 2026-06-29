"""新浪数据源测试：SinaQuoteFetcher + SinaKlineFetcher。"""

import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from fetchers.sina_quote import SinaQuoteFetcher
from fetchers.sina_kline import SinaKlineFetcher
from common.exceptions import NetworkError


class TestSinaQuoteFetcher:
    """SinaQuoteFetcher 测试。"""

    def setup_method(self):
        self.fetcher = SinaQuoteFetcher()

    def test_name_and_priority(self):
        assert self.fetcher.name == "sina_quote"
        assert self.fetcher.priority == 5

    def test_fetch_normal(self):
        """正常响应：解析新浪行情数据。"""
        raw = (
            'var hq_str_sh600519="贵州茅台,1795.00,1790.00,1800.00,1810.00,1790.00,'
            "1799.00,1800.50,1234500,2234567000.00,"
            "100,1799.00,200,1799.50,150,1798.00,250,1798.50,180,"
            "15:00:03,2025-06-12,01,10.00,0.56,1810.00,1790.00,1.12,22600.00,22600.00,"
            '8.20,2069.00,1611.00,1.00";'
        ).encode("gbk")
        with patch("fetchers.sina_quote.http_get_with_headers", return_value=raw):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert result["name"] == "贵州茅台"
        assert result["source"] == "sina"
        assert result["price"] == "1800.00"
        assert result["prev_close"] == "1790.00"
        assert result["open"] == "1795.00"
        assert result["high"] == "1810.00"
        assert result["low"] == "1790.00"
        assert result["volume"] == 1234500  # 股（新浪原值已是股）
        assert result["amount"] == 2234567000.00  # 元

    def test_fetch_change_pct_calculated(self):
        """涨跌幅由 (当前价/昨收 - 1) * 100 计算。"""
        raw = (
            'var hq_str_sh600519="贵州茅台,1795.00,100.00,110.00,115.00,95.00,'
            "105.00,108.00,1000000,100000000.00,"
            "100,105.00,200,104.00,150,103.00,250,102.00,180,"
            "15:00:03,2025-06-12,01,10.00,0.56,115.00,95.00,1.12,100.00,100.00,"
            '8.20,100.00,100.00,1.00";'
        ).encode("gbk")
        with patch("fetchers.sina_quote.http_get_with_headers", return_value=raw):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        # (110 / 100 - 1) * 100 = 10.0
        assert result["change_pct"] == "10.0"
        # 110 - 100 = 10.0
        assert result["change_amt"] == "10.0"

    def test_fetch_empty_response(self):
        """空响应：返回 None。"""
        with patch("fetchers.sina_quote.http_get_with_headers", return_value=b""):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_malformed_response(self):
        """格式错误的响应：返回 None。"""
        with patch(
            "fetchers.sina_quote.http_get_with_headers", return_value=b"not_valid"
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_fields_too_few(self):
        """字段少于 32 个：返回 None。"""
        raw = 'var hq_str_sh600519="贵州茅台,1795.00,1790.00";'.encode("gbk")
        with patch("fetchers.sina_quote.http_get_with_headers", return_value=raw):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_http_error(self):
        """HTTP 错误：异常传播。"""
        with patch(
            "fetchers.sina_quote.http_get_with_headers",
            side_effect=NetworkError("url", "err", 3),
        ):
            with pytest.raises(NetworkError):
                self.fetcher.fetch("sh600519")


class TestSinaKlineFetcher:
    """SinaKlineFetcher 测试。"""

    def setup_method(self):
        self.fetcher = SinaKlineFetcher()

    def test_name_and_priority(self):
        assert self.fetcher.name == "sina_kline"
        assert self.fetcher.priority == 10

    def test_fetch_normal(self):
        """正常响应：解析 K 线数据。"""
        data = [
            {
                "day": "2025-06-10",
                "open": "1790.00",
                "high": "1810.00",
                "low": "1785.00",
                "close": "1800.00",
                "volume": "12345",
            },
            {
                "day": "2025-06-11",
                "open": "1800.00",
                "high": "1815.00",
                "low": "1795.00",
                "close": "1805.00",
                "volume": "11000",
            },
        ]
        with patch(
            "fetchers.sina_kline.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert len(result) == 2
        assert result[0]["day"] == "2025-06-10"
        assert result[0]["source"] == "sina"
        assert result[1]["source"] == "sina"

    def test_fetch_with_params(self):
        """指定 scale 和 datalen 参数。"""
        data = [
            {
                "day": "2025-06-10",
                "open": "1790.00",
                "high": "1810.00",
                "low": "1785.00",
                "close": "1800.00",
                "volume": "12345",
            },
        ]
        with patch(
            "fetchers.sina_kline.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519", scale=60, datalen=1)
        assert result is not None
        assert len(result) == 1

    def test_fetch_empty_list(self):
        """空列表：返回 None。"""
        with patch("fetchers.sina_kline.http_get", return_value=b"[]"):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_invalid_json(self):
        """无效 JSON：返回 None。"""
        with patch("fetchers.sina_kline.http_get", return_value=b"not json"):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_http_error(self):
        """HTTP 错误：异常传播。"""
        with patch(
            "fetchers.sina_kline.http_get", side_effect=NetworkError("url", "err", 3)
        ):
            with pytest.raises(NetworkError):
                self.fetcher.fetch("sh600519")

    def test_fetch_preserves_original_fields(self):
        """K 线数据保留原始字段并添加 source。"""
        data = [
            {
                "day": "2025-06-10",
                "open": "10.00",
                "high": "11.00",
                "low": "9.50",
                "close": "10.50",
                "volume": "5000",
                "extra": "kept",
            },
        ]
        with patch(
            "fetchers.sina_kline.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert result[0]["extra"] == "kept"
