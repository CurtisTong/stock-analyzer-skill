"""东方财富事件日历数据源覆盖测试（mock http_get）。

覆盖 EarningsCalendarFetcher / LockupCalendarFetcher / DividendCalendarFetcher /
ShareholderChangeFetcher / ViolationFetcher 的解析逻辑：成功解析、code 过滤、
JSON 解析失败、success!=True、空 data、缺 code 等。
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetchers.event.eastmoney_event as ee


def _ok(rows):
    """构造 success=True 的响应 bytes。"""
    return json.dumps({"success": True, "result": {"data": rows}}).encode("utf-8")


class TestEarningsCalendar:
    def test_parse_success(self):
        rows = [
            {
                "SECURITY_CODE": "600519",
                "SECURITY_NAME_ABBR": "贵州茅台",
                "REPORT_DATE": "2025-03-31T00:00:00",
                "OP_DATE": "2025-04-15T00:00:00",
                "OP_CHANGE": "预告",
            }
        ]
        with patch.object(ee, "http_get", return_value=_ok(rows)):
            f = ee.EarningsCalendarFetcher()
            result = f.fetch()
        assert result["type"] == "earnings"
        assert len(result["items"]) == 1
        assert result["items"][0]["code"] == "600519"
        assert result["items"][0]["report_date"] == "2025-03-31"
        assert result["items"][0]["disclosure_date"] == "2025-04-15"

    def test_code_filter(self):
        rows = [
            {
                "SECURITY_CODE": "600519",
                "SECURITY_NAME_ABBR": "A",
                "REPORT_DATE": "",
                "OP_DATE": "",
                "OP_CHANGE": "",
            },
            {
                "SECURITY_CODE": "000001",
                "SECURITY_NAME_ABBR": "B",
                "REPORT_DATE": "",
                "OP_DATE": "",
                "OP_CHANGE": "",
            },
        ]
        with patch.object(ee, "http_get", return_value=_ok(rows)):
            f = ee.EarningsCalendarFetcher()
            result = f.fetch(code="sh600519")
        assert len(result["items"]) == 1
        assert result["items"][0]["code"] == "600519"

    def test_json_decode_error_returns_none(self):
        with patch.object(ee, "http_get", return_value=b"not json"):
            f = ee.EarningsCalendarFetcher()
            assert f.fetch() is None

    def test_success_false_returns_none(self):
        bad = json.dumps({"success": False, "result": {"data": []}}).encode("utf-8")
        with patch.object(ee, "http_get", return_value=bad):
            f = ee.EarningsCalendarFetcher()
            assert f.fetch() is None

    def test_empty_data_returns_none(self):
        empty = json.dumps({"success": True, "result": {"data": []}}).encode("utf-8")
        with patch.object(ee, "http_get", return_value=empty):
            f = ee.EarningsCalendarFetcher()
            assert f.fetch() is None


class TestLockupCalendar:
    def test_parse_success(self):
        rows = [
            {
                "SECURITY_CODE": "600519",
                "SECURITY_NAME_ABBR": "贵州茅台",
                "FREE_DATE": "2025-06-01",
                "LIFT_NUM": "1000000",
                "LIFT_MARKET_CAP": "2000000000",
                "NEW_PRICE": "1800.5",
            }
        ]
        with patch.object(ee, "http_get", return_value=_ok(rows)):
            f = ee.LockupCalendarFetcher()
            result = f.fetch()
        assert result["type"] == "lockup"
        assert result["items"][0]["free_date"] == "2025-06-01"
        assert result["items"][0]["lift_num"] == 1000000.0
        assert result["items"][0]["price"] == 1800.5

    def test_code_filter_excludes_others(self):
        rows = [
            {
                "SECURITY_CODE": "600519",
                "SECURITY_NAME_ABBR": "A",
                "FREE_DATE": "2025-06-01",
                "LIFT_NUM": "1",
                "LIFT_MARKET_CAP": "1",
                "NEW_PRICE": "1",
            },
            {
                "SECURITY_CODE": "000001",
                "SECURITY_NAME_ABBR": "B",
                "FREE_DATE": "2025-06-01",
                "LIFT_NUM": "1",
                "LIFT_MARKET_CAP": "1",
                "NEW_PRICE": "1",
            },
        ]
        with patch.object(ee, "http_get", return_value=_ok(rows)):
            f = ee.LockupCalendarFetcher()
            result = f.fetch(code="sh600519")
        assert len(result["items"]) == 1

    def test_json_decode_error(self):
        with patch.object(ee, "http_get", return_value=b"xxx"):
            f = ee.LockupCalendarFetcher()
            assert f.fetch() is None


class TestDividendCalendar:
    def test_parse_success(self):
        rows = [
            {
                "SECURITY_CODE": "600519",
                "SECURITY_NAME_ABBR": "贵州茅台",
                "EX_DIVIDEND_DATE": "2025-07-01",
                "PRETAX_BONUS_RMB": "25.91",
                "PLAN_NOTICE_DATE": "2025-03-28",
                "REG_DATE": "2025-06-30",
            }
        ]
        with patch.object(ee, "http_get", return_value=_ok(rows)):
            f = ee.DividendCalendarFetcher()
            result = f.fetch()
        assert result["type"] == "dividend"
        assert result["items"][0]["ex_date"] == "2025-07-01"
        assert result["items"][0]["bonus_per_share"] == 25.91

    def test_empty_data_returns_none(self):
        empty = json.dumps({"success": True, "result": {"data": []}}).encode("utf-8")
        with patch.object(ee, "http_get", return_value=empty):
            f = ee.DividendCalendarFetcher()
            assert f.fetch() is None


class TestShareholderChange:
    def test_no_code_returns_none(self):
        f = ee.ShareholderChangeFetcher()
        assert f.fetch(code="") is None

    def test_parse_success_increase(self):
        rows = [
            {
                "SECURITY_CODE": "600519",
                "SECURITY_NAME_ABBR": "贵州茅台",
                "HOLDER_NAME": "大股东",
                "END_DATE": "2025-05-01",
                "CHANGE_NUM": "100000",
                "CHANGE_RATIO": "0.5",
                "AVERAGE_PRICE": "1800",
                "CHANGE_SHARES_AFTER": "500000",
            }
        ]
        with patch.object(ee, "http_get", return_value=_ok(rows)):
            f = ee.ShareholderChangeFetcher()
            result = f.fetch(code="sh600519")
        assert result["type"] == "shareholder"
        assert result["items"][0]["direction"] == "increase"
        assert result["items"][0]["change_num"] == 100000.0

    def test_decrease_direction(self):
        rows = [
            {
                "SECURITY_CODE": "600519",
                "SECURITY_NAME_ABBR": "A",
                "HOLDER_NAME": "X",
                "END_DATE": "",
                "CHANGE_NUM": "-5000",
                "CHANGE_RATIO": "0",
                "AVERAGE_PRICE": "0",
                "CHANGE_SHARES_AFTER": "0",
            }
        ]
        with patch.object(ee, "http_get", return_value=_ok(rows)):
            f = ee.ShareholderChangeFetcher()
            result = f.fetch(code="sh600519")
        assert result["items"][0]["direction"] == "decrease"

    def test_json_decode_error(self):
        with patch.object(ee, "http_get", return_value=b"bad"):
            f = ee.ShareholderChangeFetcher()
            assert f.fetch(code="sh600519") is None


class TestViolation:
    def test_no_code_returns_none(self):
        f = ee.ViolationFetcher()
        assert f.fetch(code="") is None

    def test_parse_success(self):
        rows = [
            {
                "SECURITY_CODE": "600519",
                "SECURITY_NAME_ABBR": "贵州茅台",
                "PUNISH_DATE": "2025-04-01",
                "PUNISH_CONTENT": "警告",
                "PUNISH_REASON": "违规",
                "REGULATOR": "证监会",
            }
        ]
        with patch.object(ee, "http_get", return_value=_ok(rows)):
            f = ee.ViolationFetcher()
            result = f.fetch(code="sh600519")
        assert result["type"] == "violation"
        assert result["items"][0]["punish_date"] == "2025-04-01"
        assert result["items"][0]["regulator"] == "证监会"

    def test_empty_data_returns_none(self):
        empty = json.dumps({"success": True, "result": {"data": []}}).encode("utf-8")
        with patch.object(ee, "http_get", return_value=empty):
            f = ee.ViolationFetcher()
            assert f.fetch(code="sh600519") is None
