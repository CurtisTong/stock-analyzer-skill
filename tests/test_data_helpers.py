"""data/helpers.py 单元测试：数据获取便捷函数。"""

import pytest
from unittest.mock import patch, MagicMock

from data.types import Quote, KlineBar, FinanceRecord


class TestFetchQuoteDict:
    """fetch_quote_dict 测试。"""

    def test_returns_dict(self):
        from data.helpers import fetch_quote_dict

        mock_q = Quote(code="sh600989", name="宝丰能源", price=18.5)
        with patch("data.helpers.get_quote", return_value=mock_q):
            result = fetch_quote_dict("sh600989")

        assert result["code"] == "sh600989"
        assert result["price"] == 18.5

    def test_returns_empty_when_none(self):
        from data.helpers import fetch_quote_dict

        with patch("data.helpers.get_quote", return_value=None):
            result = fetch_quote_dict("invalid")

        assert result == {}


class TestFetchQuoteDictOrNone:
    """fetch_quote_dict_or_none 测试。"""

    def test_returns_dict(self):
        from data.helpers import fetch_quote_dict_or_none

        mock_q = Quote(code="sh600989", price=18.5)
        with patch("data.helpers.get_quote", return_value=mock_q):
            result = fetch_quote_dict_or_none("sh600989")

        assert result is not None
        assert result["price"] == 18.5

    def test_returns_none(self):
        from data.helpers import fetch_quote_dict_or_none

        with patch("data.helpers.get_quote", return_value=None):
            result = fetch_quote_dict_or_none("invalid")

        assert result is None


class TestFetchBatchDicts:
    """fetch_batch_dicts 测试。"""

    def test_returns_list_of_dicts(self):
        from data.helpers import fetch_batch_dicts

        quotes = [
            Quote(code="sh600989", price=18.5),
            Quote(code="sz000807", price=15.0),
        ]
        with patch("data.helpers.get_quotes", return_value=quotes):
            result = fetch_batch_dicts(["sh600989", "sz000807"])

        assert len(result) == 2
        assert result[0]["code"] == "sh600989"
        assert result[1]["code"] == "sz000807"

    def test_empty_codes(self):
        from data.helpers import fetch_batch_dicts

        with patch("data.helpers.get_quotes", return_value=[]):
            result = fetch_batch_dicts([])

        assert result == []


class TestFetchKlineDicts:
    """fetch_kline_dicts 测试。"""

    def test_returns_list_of_dicts(self):
        from data.helpers import fetch_kline_dicts

        bars = [
            KlineBar(day="2025-06-20", close=18.5),
            KlineBar(day="2025-06-19", close=18.0),
        ]
        with patch("data.helpers.get_kline", return_value=bars):
            result = fetch_kline_dicts("sh600989")

        assert len(result) == 2
        assert result[0]["day"] == "2025-06-20"
        assert result[1]["close"] == 18.0

    def test_passes_parameters(self):
        from data.helpers import fetch_kline_dicts

        with patch("data.helpers.get_kline", return_value=[]) as mock:
            fetch_kline_dicts("sh600989", scale=60, datalen=50)
            mock.assert_called_once_with("sh600989", scale=60, datalen=50)


class TestFetchFinanceDicts:
    """fetch_finance_dicts 测试。"""

    def test_returns_list_of_dicts(self):
        from data.helpers import fetch_finance_dicts

        records = [FinanceRecord(report_date="2025-03-31", eps=0.5, roe=15.0)]
        with patch("data.helpers.get_finance", return_value=records):
            result = fetch_finance_dicts("sh600989")

        assert len(result) == 1
        assert result[0]["eps"] == 0.5


class TestFetchFinanceFirst:
    """fetch_finance_first 测试。"""

    def test_returns_first_record(self):
        from data.helpers import fetch_finance_first

        records = [
            FinanceRecord(report_date="2025-03-31", eps=0.5),
            FinanceRecord(report_date="2024-12-31", eps=0.4),
        ]
        with patch("data.helpers.get_finance", return_value=records):
            result = fetch_finance_first("sh600989")

        assert result["report_date"] == "2025-03-31"

    def test_returns_empty_when_no_data(self):
        from data.helpers import fetch_finance_first

        with patch("data.helpers.get_finance", return_value=[]):
            result = fetch_finance_first("invalid")

        assert result == {}
