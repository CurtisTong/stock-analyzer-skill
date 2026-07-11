import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestExceptions:
    def test_stock_analyzer_error(self):
        from common.exceptions import StockAnalyzerError
        e = StockAnalyzerError("test")
        assert str(e) == "test"

    def test_data_error(self):
        from common.exceptions import DataError, StockAnalyzerError
        e = DataError("test")
        assert isinstance(e, StockAnalyzerError)

    def test_network_error(self):
        from common.exceptions import NetworkError, DataError
        e = NetworkError("url", "msg")
        assert isinstance(e, DataError)

    def test_rate_limit_error(self):
        from common.exceptions import RateLimitError, NetworkError
        e = RateLimitError("url", retry_after=60)
        assert isinstance(e, NetworkError)
        assert e.retry_after == 60

    def test_http_status_error(self):
        from common.exceptions import HTTPStatusError, DataError
        e = HTTPStatusError("url", 404, "Not Found")
        assert isinstance(e, DataError)
        assert hasattr(e, 'status_code') or hasattr(e, 'status')

    def test_format_error(self):
        from common.exceptions import format_error, NetworkError
        e = NetworkError("url", "timeout")
        msg = format_error(e)
        assert isinstance(msg, str)

    def test_is_retryable_error(self):
        from common.exceptions import is_retryable_error, NetworkError, HTTPStatusError
        assert is_retryable_error(NetworkError("url", "timeout")) is True
        assert is_retryable_error(HTTPStatusError("url", 404, "")) is False
