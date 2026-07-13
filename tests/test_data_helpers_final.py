import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


import data.helpers as helpers_mod  # noqa: E402


class TestFetchKlineDicts:
    def test_empty(self):
        with patch.object(helpers_mod, "get_kline", return_value=[]):
            assert helpers_mod.fetch_kline_dicts("sh600519") == []

    def test_with_data(self):
        mock_bar = MagicMock()
        mock_bar.to_dict.return_value = {"day": "2026-01-01", "close": 10}
        with patch.object(helpers_mod, "get_kline", return_value=[mock_bar]):
            result = helpers_mod.fetch_kline_dicts("sh600519")
            assert isinstance(result, list)


class TestFetchFinanceDicts:
    def test_empty(self):
        with patch.object(helpers_mod, "get_finance", return_value=[]):
            assert helpers_mod.fetch_finance_dicts("sh600519") == []

    def test_with_data(self):
        mock_rec = MagicMock()
        mock_rec.to_dict.return_value = {"report_date": "2026-01-01"}
        with patch.object(helpers_mod, "get_finance", return_value=[mock_rec]):
            result = helpers_mod.fetch_finance_dicts("sh600519")
            assert isinstance(result, list)


class TestFetchStockBundle:
    def test_returns_dict(self):
        mock_q = MagicMock()
        mock_q.to_dict.return_value = {"code": "sh600519"}
        with patch.object(helpers_mod, "get_quote", return_value=mock_q), \
             patch.object(helpers_mod, "get_kline", return_value=[]), \
             patch.object(helpers_mod, "get_finance", return_value=[]):
            result = helpers_mod.fetch_stock_bundle("sh600519")
            assert isinstance(result, dict)
