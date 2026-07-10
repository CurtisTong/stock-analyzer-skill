"""东方财富数据源测试：EastmoneyQuoteFetcher + EastmoneyKlineFetcher + EastmoneyFinanceFetcher。"""

import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from fetchers.quote.eastmoney_quote import EastmoneyQuoteFetcher
from fetchers.kline.eastmoney_kline import EastmoneyKlineFetcher
from fetchers.finance.eastmoney_finance import EastmoneyFinanceFetcher
from common.exceptions import NetworkError


class TestEastmoneyQuoteFetcher:
    """EastmoneyQuoteFetcher 测试。"""

    def setup_method(self):
        self.fetcher = EastmoneyQuoteFetcher()

    def test_name_and_priority(self):
        assert self.fetcher.name == "eastmoney_quote"
        assert self.fetcher.priority == 8

    def test_fetch_normal(self):
        """正常响应：解析东财行情数据。"""
        data = {
            "rc": 0,
            "data": {
                "f57": "600519",
                "f58": "贵州茅台",
                "f43": 180000,  # price * 100
                "f60": 179000,  # prev_close * 100
                "f46": 179500,  # open * 100
                "f170": 56,  # change_pct * 100
                "f169": 1000,  # change_amt * 100
                "f44": 181000,  # high * 100
                "f45": 179000,  # low * 100
                "f47": 12345,  # volume
                "f48": 22345670000,  # amount
                "f168": 15,  # turnover * 100
                "f162": 2560,  # pe * 100
                "f167": 820,  # pb * 100
                "f116": 2260000000000,  # total_cap
                "f117": 2260000000000,  # circulating_cap
            },
        }
        with patch(
            "fetchers.quote.eastmoney_quote.http_get",
            return_value=json.dumps(data).encode(),
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert result["code"] == "600519"
        assert result["name"] == "贵州茅台"
        assert result["source"] == "eastmoney"
        assert result["price"] == "1800.0"  # 180000 / 100
        assert result["prev_close"] == "1790.0"
        assert result["open"] == "1795.0"
        assert result["change_pct"] == "0.56"

    def test_fetch_empty_response(self):
        """空 JSON 对象：返回 None。"""
        with patch("fetchers.quote.eastmoney_quote.http_get", return_value=b"{}"):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_invalid_json(self):
        """无效 JSON：返回 None。"""
        with patch("fetchers.quote.eastmoney_quote.http_get", return_value=b"not json"):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_rc_not_zero(self):
        """rc != 0：返回 None。"""
        data = {"rc": -1, "data": {}}
        with patch(
            "fetchers.quote.eastmoney_quote.http_get",
            return_value=json.dumps(data).encode(),
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_no_data_key(self):
        """缺少 data 字段：返回 None。"""
        data = {"rc": 0}
        with patch(
            "fetchers.quote.eastmoney_quote.http_get",
            return_value=json.dumps(data).encode(),
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_data_is_none(self):
        """data 为 None：返回 None。"""
        data = {"rc": 0, "data": None}
        with patch(
            "fetchers.quote.eastmoney_quote.http_get",
            return_value=json.dumps(data).encode(),
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_code_padded(self):
        """代码不足 6 位时补零。"""
        data = {
            "rc": 0,
            "data": {
                "f57": "858",
                "f58": "五粮液",
                "f43": 180000,
                "f60": 179000,
                "f46": 179500,
                "f170": 56,
                "f169": 1000,
                "f44": 181000,
                "f45": 179000,
                "f47": 12345,
                "f48": 22345670000,
                "f168": 15,
                "f162": 2560,
                "f167": 820,
                "f116": 2260000000000,
                "f117": 2260000000000,
            },
        }
        with patch(
            "fetchers.quote.eastmoney_quote.http_get",
            return_value=json.dumps(data).encode(),
        ):
            result = self.fetcher.fetch("sz000858")
        assert result is not None
        assert result["code"] == "000858"

    def test_fetch_http_error(self):
        """HTTP 错误：异常传播。"""
        with patch(
            "fetchers.quote.eastmoney_quote.http_get",
            side_effect=NetworkError("url", "err", 3),
        ):
            with pytest.raises(NetworkError):
                self.fetcher.fetch("sh600519")


class TestEastmoneyKlineFetcher:
    """EastmoneyKlineFetcher 测试。"""

    def setup_method(self):
        self.fetcher = EastmoneyKlineFetcher()

    def test_name_and_priority(self):
        assert self.fetcher.name == "eastmoney_kline"
        assert self.fetcher.priority == 8

    def test_fetch_normal(self):
        """正常响应：解析 K 线数据。"""
        data = {
            "rc": 0,
            "data": {
                "klines": [
                    "2025-06-10,1790.00,1800.00,1810.00,1785.00,12345,2234567,1.12,25.00,1.50,180000",
                    "2025-06-11,1800.00,1805.00,1815.00,1795.00,11000,2000000,0.56,18.00,0.80,180500",
                ],
            },
        }
        with patch(
            "fetchers.kline.eastmoney_kline.http_get",
            return_value=json.dumps(data).encode(),
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert len(result) == 2
        assert result[0]["day"] == "2025-06-10"
        assert result[0]["source"] == "eastmoney"
        assert result[0]["open"] == "1790.00"
        assert result[0]["close"] == "1800.00"
        assert result[0]["high"] == "1810.00"
        assert result[0]["low"] == "1785.00"
        assert result[0]["volume"] == "12345"
        assert result[0]["amount"] == "2234567"
        assert result[0]["pct_chg"] == "25.00"

    def test_fetch_with_scale(self):
        """指定 scale 参数。"""
        data = {
            "rc": 0,
            "data": {
                "klines": [
                    "2025-06-10,1790.00,1800.00,1810.00,1785.00,12345,2234567,1.12,25.00,1.50,180000",
                ],
            },
        }
        with patch(
            "fetchers.kline.eastmoney_kline.http_get",
            return_value=json.dumps(data).encode(),
        ):
            result = self.fetcher.fetch("sh600519", scale=60, datalen=1)
        assert result is not None
        assert len(result) == 1

    def test_fetch_empty_response(self):
        """空响应：返回 None。"""
        with patch("fetchers.kline.eastmoney_kline.http_get", return_value=b"{}"):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_invalid_json(self):
        """无效 JSON：返回 None。"""
        with patch("fetchers.kline.eastmoney_kline.http_get", return_value=b"bad"):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_rc_not_zero(self):
        """rc != 0：返回 None。"""
        data = {"rc": -1, "data": {}}
        with patch(
            "fetchers.kline.eastmoney_kline.http_get",
            return_value=json.dumps(data).encode(),
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_empty_klines(self):
        """klines 为空列表：返回 None。"""
        data = {"rc": 0, "data": {"klines": []}}
        with patch(
            "fetchers.kline.eastmoney_kline.http_get",
            return_value=json.dumps(data).encode(),
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_short_line_skipped(self):
        """行字段不足 6 个时被跳过。"""
        data = {
            "rc": 0,
            "data": {
                "klines": [
                    "2025-06-10,1790.00,1800.00",  # 不足 6 字段
                    "2025-06-11,1800.00,1805.00,1815.00,1795.00,11000,2000000",
                ],
            },
        }
        with patch(
            "fetchers.kline.eastmoney_kline.http_get",
            return_value=json.dumps(data).encode(),
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert len(result) == 1

    def test_fetch_http_error(self):
        """HTTP 错误：异常传播。"""
        with patch(
            "fetchers.kline.eastmoney_kline.http_get",
            side_effect=NetworkError("url", "err", 3),
        ):
            with pytest.raises(NetworkError):
                self.fetcher.fetch("sh600519")


class TestEastmoneyFinanceFetcher:
    """EastmoneyFinanceFetcher 测试。"""

    def setup_method(self):
        self.fetcher = EastmoneyFinanceFetcher()

    def test_name_and_priority(self):
        assert self.fetcher.name == "eastmoney_finance"
        assert self.fetcher.priority == 10

    def test_fetch_normal(self):
        """正常响应：解析财务数据。"""
        data = {
            "data": [
                {"REPORT_DATE": "2025-03-31", "EPSJB": "15.00", "ROEJQ": "8.5"},
                {"REPORT_DATE": "2024-12-31", "EPSJB": "50.00", "ROEJQ": "30.5"},
            ],
        }
        with patch(
            "fetchers.finance.eastmoney_finance.http_get",
            return_value=json.dumps(data).encode(),
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert len(result) == 2
        assert result[0]["source"] == "eastmoney"
        assert result[0]["EPSJB"] == "15.00"

    def test_fetch_truncated_to_4(self):
        """返回最多 4 条记录。"""
        data = {
            "data": [
                {"REPORT_DATE": f"2025-0{i}-31", "EPSJB": str(i)} for i in range(1, 8)
            ],
        }
        with patch(
            "fetchers.finance.eastmoney_finance.http_get",
            return_value=json.dumps(data).encode(),
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert len(result) == 4

    def test_fetch_empty_response(self):
        """空响应：返回 None。"""
        with patch("fetchers.finance.eastmoney_finance.http_get", return_value=b"{}"):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_invalid_json(self):
        """无效 JSON：返回 None。"""
        with patch("fetchers.finance.eastmoney_finance.http_get", return_value=b"bad"):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_no_data_key(self):
        """缺少 data 字段：返回 None。"""
        data = {"other": "value"}
        with patch(
            "fetchers.finance.eastmoney_finance.http_get",
            return_value=json.dumps(data).encode(),
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_empty_data_list(self):
        """data 为空列表：返回 None。"""
        data = {"data": []}
        with patch(
            "fetchers.finance.eastmoney_finance.http_get",
            return_value=json.dumps(data).encode(),
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_http_error(self):
        """HTTP 错误：异常传播。"""
        with patch(
            "fetchers.finance.eastmoney_finance.http_get",
            side_effect=NetworkError("url", "err", 3),
        ):
            with pytest.raises(NetworkError):
                self.fetcher.fetch("sh600519")
