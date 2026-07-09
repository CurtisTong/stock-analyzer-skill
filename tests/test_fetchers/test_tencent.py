"""腾讯数据源测试：TencentQuoteFetcher + TencentKlineFetcher。"""

import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from fetchers.quote.tencent_quote import TencentQuoteFetcher
from fetchers.kline.tencent_kline import TencentKlineFetcher
from common.exceptions import NetworkError


def _make_tencent_raw(**overrides):
    """构造腾讯行情 raw bytes，字段位置与 parse_tencent_line 一致。

    TENCENT_FIELDS 中的关键索引:
      0=market, 1=name, 2=code, 3=price, 4=prev_close, 5=open,
      31=change_amt, 32=change_pct, 33=high, 34=low,
      36=volume(手), 37=amount(万), 38=turnover, 39=pe,
      44=total_cap, 45=circulating_cap, 46=pb
    """
    fields = [""] * 50
    fields[0] = "1"
    fields[1] = "贵州茅台"
    fields[2] = "600519"
    fields[3] = "1800.00"
    fields[4] = "1790.00"
    fields[5] = "1795.00"
    fields[31] = "10.00"
    fields[32] = "0.56"
    fields[33] = "1810.00"
    fields[34] = "1790.00"
    fields[36] = "12345"
    fields[37] = "2234567"
    fields[38] = "0.15"
    fields[39] = "25.60"
    fields[44] = "22600.00"
    fields[45] = "22600.00"
    fields[46] = "8.20"
    for k, v in overrides.items():
        fields[k] = v
    line = "~".join(fields)
    return ('v_sh600519="' + line + '";').encode("gbk")


class TestTencentQuoteFetcher:
    """TencentQuoteFetcher 测试。"""

    def setup_method(self):
        self.fetcher = TencentQuoteFetcher()

    def test_name_and_priority(self):
        assert self.fetcher.name == "tencent_quote"
        assert self.fetcher.priority == 10

    def test_fetch_normal(self):
        """正常响应：解析腾讯行情数据。"""
        raw = _make_tencent_raw()
        with patch("fetchers.quote.tencent_quote.http_get", return_value=raw):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert result["code"] == "600519"
        assert result["name"] == "贵州茅台"
        assert result["source"] == "tencent"
        # volume/amount 保留数据源原始字符串（手/万元），归一化在 data 层 _dict_to_quote 统一进行
        assert result["volume"] == "12345"
        assert result["amount"] == "2234567"

    def test_fetch_empty_response(self):
        """空响应：返回 None。"""
        with patch("fetchers.quote.tencent_quote.http_get", return_value=b""):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_malformed_response(self):
        """格式错误的响应：返回 None。"""
        with patch("fetchers.quote.tencent_quote.http_get", return_value=b"not_valid_data"):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_http_error(self):
        """HTTP 错误：异常传播。"""
        with patch(
            "fetchers.quote.tencent_quote.http_get", side_effect=NetworkError("url", "err", 3)
        ):
            with pytest.raises(NetworkError):
                self.fetcher.fetch("sh600519")

    def test_fetch_fields_missing_short_line(self):
        """字段不足（行字段少于 50）：返回 None。"""
        short = 'v_sh600519="1~贵州茅台~600519~1800.00";'.encode("gbk")
        with patch("fetchers.quote.tencent_quote.http_get", return_value=short):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_multiple_lines(self):
        """多行响应：返回第一行有效数据。"""
        raw = _make_tencent_raw()
        # 追加一个空行
        multi = raw + b"\n"
        with patch("fetchers.quote.tencent_quote.http_get", return_value=multi):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert result["code"] == "600519"

    def test_fetch_code_mismatch_skipped(self):
        """P1-01: code 不匹配的行应被跳过，不返回错误记录。"""
        # 构造一个 code=600999（非请求的 600519）的有效行
        raw = _make_tencent_raw()
        # 替换 payload 内部的 code 字段（~600519~ -> ~600999~），保留 v_sh 前缀
        raw_wrong = raw.replace(b"~600519~", b"~600999~", 1)
        with patch("fetchers.quote.tencent_quote.http_get", return_value=raw_wrong):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_code_mismatch_then_match(self):
        """P1-01: 多行响应中先有错误 code 再有正确 code，应返回正确记录。"""
        wrong = _make_tencent_raw()
        wrong = wrong.replace(b"~600519~", b"~600999~", 1)
        correct = _make_tencent_raw()
        # 用分号拼接两行
        multi = wrong.rstrip(b';\n') + b";" + correct
        with patch("fetchers.quote.tencent_quote.http_get", return_value=multi):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert result["code"] == "600519"


class TestTencentKlineFetcher:
    """TencentKlineFetcher 测试。"""

    def setup_method(self):
        self.fetcher = TencentKlineFetcher()

    def test_name_and_priority(self):
        assert self.fetcher.name == "tencent_kline"
        assert self.fetcher.priority == 5

    def test_fetch_normal(self):
        """正常响应：解析 K 线数据。"""
        data = {
            "code": 0,
            "data": {
                "sh600519": {
                    "qfqday": [
                        [
                            "2025-06-10",
                            "1790.00",
                            "1800.00",
                            "1810.00",
                            "1785.00",
                            "12345",
                        ],
                        [
                            "2025-06-11",
                            "1800.00",
                            "1805.00",
                            "1815.00",
                            "1795.00",
                            "11000",
                        ],
                    ]
                }
            },
        }
        with patch(
            "fetchers.kline.tencent_kline.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert len(result) == 2
        assert result[0]["day"] == "2025-06-10"
        assert result[0]["source"] == "tencent"
        # 腾讯 K 线字段顺序: day, open, close, high, low, volume
        assert result[0]["open"] == "1790.00"
        assert result[0]["close"] == "1800.00"
        assert result[0]["high"] == "1810.00"
        assert result[0]["low"] == "1785.00"

    def test_fetch_normal_with_scale(self):
        """指定 scale 参数。"""
        data = {
            "code": 0,
            "data": {
                "sh600519": {
                    "qfqday": [
                        [
                            "2025-06-10",
                            "1790.00",
                            "1800.00",
                            "1810.00",
                            "1785.00",
                            "12345",
                        ],
                    ]
                }
            },
        }
        with patch(
            "fetchers.kline.tencent_kline.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519", scale=240, datalen=1)
        assert result is not None
        assert len(result) == 1

    def test_fetch_empty_json(self):
        """空 JSON 响应：返回 None。"""
        with patch("fetchers.kline.tencent_kline.http_get", return_value=b""):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_invalid_json(self):
        """无效 JSON：返回 None。"""
        with patch("fetchers.kline.tencent_kline.http_get", return_value=b"not json"):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_code_not_zero(self):
        """code != 0：返回 None。"""
        data = {"code": -1, "data": {}}
        with patch(
            "fetchers.kline.tencent_kline.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_no_data_key(self):
        """缺少 data 字段：返回 None。"""
        data = {"code": 0}
        with patch(
            "fetchers.kline.tencent_kline.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_empty_kline_array(self):
        """K 线数组为空：返回 None。"""
        data = {"code": 0, "data": {"sh600519": {"qfqday": []}}}
        with patch(
            "fetchers.kline.tencent_kline.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_short_row_skipped(self):
        """行字段不足 6 个时被跳过。"""
        data = {
            "code": 0,
            "data": {
                "sh600519": {
                    "qfqday": [
                        ["2025-06-10", "1790.00"],  # 不足 6 字段
                        [
                            "2025-06-11",
                            "1800.00",
                            "1805.00",
                            "1815.00",
                            "1795.00",
                            "11000",
                        ],
                    ]
                }
            },
        }
        with patch(
            "fetchers.kline.tencent_kline.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert len(result) == 1

    def test_fetch_http_error(self):
        """HTTP 错误：异常传播。"""
        with patch(
            "fetchers.kline.tencent_kline.http_get", side_effect=NetworkError("url", "err", 3)
        ):
            with pytest.raises(NetworkError):
                self.fetcher.fetch("sh600519")
