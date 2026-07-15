import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestFetchersInit:
    def test_get_quote_fetchers(self):
        from fetchers import get_quote_fetchers

        result = get_quote_fetchers()
        assert isinstance(result, list)

    def test_get_kline_fetchers(self):
        from fetchers import get_kline_fetchers

        result = get_kline_fetchers()
        assert isinstance(result, list)

    def test_get_finance_fetchers(self):
        from fetchers import get_finance_fetchers

        result = get_finance_fetchers()
        assert isinstance(result, list)

    def test_get_flow_fetchers(self):
        from fetchers import get_flow_fetchers

        result = get_flow_fetchers()
        assert isinstance(result, list)
