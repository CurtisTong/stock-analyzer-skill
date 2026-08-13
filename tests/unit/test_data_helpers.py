"""data.helpers 包装函数单元测试。

覆盖 data/helpers.py 的便捷包装函数（fetch_* / prefetch_*），
通过 monkeypatch 替代 underlying fetch 避免真实网络。
"""

from unittest.mock import patch

from data.helpers import (
    fetch_batch_dicts,
    fetch_finance_dicts,
    fetch_finance_first,
    fetch_finance_first_with_meta,
    fetch_kline_dicts,
    fetch_quote_dict,
    fetch_quote_dict_or_none,
    prefetch_finance_all,
)
from data.types import FinanceMeta, KlineBar, Quote


class TestFetchQuoteDict:
    """fetch_quote_dict / fetch_quote_dict_or_none。"""

    def test_returns_dict_when_quote_exists(self):
        q = Quote(code="sh600989", price=10.5)
        with patch("data.helpers.get_quote", return_value=q):
            d = fetch_quote_dict("sh600989")
        assert d == q.to_dict()
        assert d["code"] == "sh600989"
        assert d["price"] == 10.5

    def test_returns_empty_dict_when_none(self):
        with patch("data.helpers.get_quote", return_value=None):
            assert fetch_quote_dict("sh600989") == {}

    def test_or_none_returns_none(self):
        with patch("data.helpers.get_quote", return_value=None):
            assert fetch_quote_dict_or_none("sh600989") is None

    def test_or_none_returns_dict(self):
        q = Quote(code="sh600989", price=10.5)
        with patch("data.helpers.get_quote", return_value=q):
            assert fetch_quote_dict_or_none("sh600989") == q.to_dict()


class TestFetchBatch:
    """fetch_batch_dicts / fetch_kline_dicts。"""

    def test_returns_list_of_dicts(self):
        quotes = [Quote(code="sh600989"), Quote(code="sz000001")]
        with patch("data.helpers.get_quotes", return_value=quotes):
            result = fetch_batch_dicts(["sh600989", "sz000001"])
        assert len(result) == 2
        assert result[0]["code"] == "sh600989"
        assert result[1]["code"] == "sz000001"

    def test_empty_input(self):
        with patch("data.helpers.get_quotes", return_value=[]):
            assert fetch_batch_dicts([]) == []

    def test_kline_dicts_converts_bars(self):
        bar = KlineBar(day="2026-08-11", close=10.5)
        with patch("data.helpers.get_kline", return_value=[bar]):
            result = fetch_kline_dicts("sh600989", scale=240, datalen=30)
        assert len(result) == 1
        assert result[0]["day"] == "2026-08-11"
        assert result[0]["close"] == 10.5

    def test_kline_dicts_empty(self):
        with patch("data.helpers.get_kline", return_value=[]):
            assert fetch_kline_dicts("sh600989") == []


class TestFetchFinance:
    """fetch_finance_dicts / fetch_finance_first / fetch_finance_first_with_meta。"""

    def _fake_finance(self):
        from data import _dict_to_finance

        return [
            _dict_to_finance({"EPSJB": "1.5", "ROEJQ": "15.0", "source": "eastmoney"})
        ]

    def test_finance_dicts_returns_records(self):
        records = self._fake_finance()
        with patch("data.helpers.get_finance", return_value=(records, FinanceMeta())):
            result = fetch_finance_dicts("sh600989")
        assert len(result) == 1
        assert result[0]["eps"] == 1.5
        assert result[0]["roe"] == 15.0

    def test_finance_first_returns_first_record(self):
        records = self._fake_finance()
        with patch("data.helpers.get_finance", return_value=(records, FinanceMeta())):
            d = fetch_finance_first("sh600989")
        assert d["eps"] == 1.5

    def test_finance_first_empty_returns_empty_dict(self):
        with patch("data.helpers.get_finance", return_value=([], FinanceMeta())):
            assert fetch_finance_first("sh600989") == {}

    def test_first_with_meta_returns_meta(self):
        records = self._fake_finance()
        meta = FinanceMeta(source="eastmoney", requested_periods=4, actual_periods=1)
        with patch("data.helpers.get_finance", return_value=(records, meta)):
            d, m = fetch_finance_first_with_meta("sh600989")
        assert d["eps"] == 1.5
        assert m.source == "eastmoney"
        assert m.actual_periods == 1

    def test_first_with_meta_empty_returns_empty_dict_and_default_meta(self):
        with patch("data.helpers.get_finance", return_value=([], None)):
            d, m = fetch_finance_first_with_meta("sh600989")
        assert d == {}
        assert isinstance(m, FinanceMeta)
        assert m.source == ""


class TestPrefetchFinanceAll:
    """prefetch_finance_all 批量预取。"""

    def test_returns_code_mapped_records(self):
        with patch(
            "data.helpers.get_finance",
            return_value=([], FinanceMeta()),
        ):
            with patch(
                "common.normalize_finance_code", side_effect=lambda c: c.upper()
            ):
                result = prefetch_finance_all(["sh600989", "sz000001"])
        assert result["sh600989"] == []
        assert result["sz000001"] == []

    def test_single_entry_failure_yields_empty_list(self):
        """单条 fetch 抛异常 → 该 code 置空，不中断整批。"""
        from common.exceptions import DataError

        real = []

        def fake_get_finance(code, **kw):
            real.append(code)
            if "fail" in code:
                raise DataError("mock fail")
            return ([], FinanceMeta())

        with patch("data.helpers.get_finance", side_effect=fake_get_finance):
            with patch("common.normalize_finance_code", side_effect=lambda c: c):
                result = prefetch_finance_all(["sh600989", "szfail"])
        assert result["sh600989"] == []
        assert result["szfail"] == []
        assert len(real) == 2
