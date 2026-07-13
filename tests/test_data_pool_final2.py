import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import data.pool as pool_mod  # noqa: E402


class TestFetchPush2Market:
    def test_no_boards(self):
        pool_mod._fetch_push2_market({})
        # Should not raise

    def test_with_boards(self):
        with patch("common.http.http_get", return_value=b'{"data":{"diff":[]}}'):
            pool_mod._fetch_push2_market({"消费": ["sh600519"]})


class TestPassesFilterMore:
    def test_etf(self):
        stock = {"name": "沪深300ETF", "code": "sh510300"}
        passed, _ = pool_mod.passes_filter(stock)
        assert isinstance(passed, bool)

    def test_empty_name(self):
        stock = {"name": "", "code": "sh600519"}
        passed, _ = pool_mod.passes_filter(stock)
        assert isinstance(passed, bool)
