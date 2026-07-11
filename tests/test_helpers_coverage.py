import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import data.helpers as helpers_mod  # noqa: E402


class TestFetchQuoteDict:
    def test_returns_dict(self):
        mock_q = MagicMock()
        mock_q.to_dict.return_value = {"code": "sh600519", "price": 1800}
        with patch.object(helpers_mod, "get_quote", return_value=mock_q):
            result = helpers_mod.fetch_quote_dict("sh600519")
            assert isinstance(result, dict)

    def test_returns_none(self):
        with patch.object(helpers_mod, "get_quote", return_value=None):
            assert helpers_mod.fetch_quote_dict_or_none("sh600519") is None


class TestFetchBatchDicts:
    def test_empty(self):
        assert helpers_mod.fetch_batch_dicts([]) == []


class TestFetchFinanceFirst:
    def test_no_data(self):
        with patch.object(helpers_mod, "get_finance", return_value=[]):
            assert helpers_mod.fetch_finance_first("sh600519") == {}
