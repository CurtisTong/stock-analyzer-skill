import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestExceptionChaining:
    def test_data_error_chains(self):
        from common.exceptions import DataError, StockAnalyzerError
        e = DataError("test")
        assert isinstance(e, StockAnalyzerError)

    def test_business_error_chains(self):
        from common.exceptions import BusinessError, StockAnalyzerError
        e = BusinessError("msg")
        assert isinstance(e, StockAnalyzerError)

    def test_validation_error_chains(self):
        from common.exceptions import ValidationError, BusinessError
        e = ValidationError("field", "value", "invalid")
        assert isinstance(e, BusinessError)

    def test_strategy_error_chains(self):
        from common.exceptions import StrategyError, BusinessError
        e = StrategyError("msg")
        assert isinstance(e, BusinessError)

    def test_insufficient_data(self):
        from common.exceptions import InsufficientDataError, DataError
        e = InsufficientDataError("msg")
        assert isinstance(e, DataError)

    def test_configuration_error(self):
        from common.exceptions import ConfigurationError, StockAnalyzerError
        e = ConfigurationError("msg")
        assert isinstance(e, StockAnalyzerError)

class TestFormatErrorMore:
    def test_network_error_format(self):
        from common.exceptions import format_error, NetworkError
        e = NetworkError("http://test.com", "timeout")
        msg = format_error(e)
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_generic_error_format(self):
        from common.exceptions import format_error
        msg = format_error(ValueError("test"))
        assert isinstance(msg, str)

class TestIsRetryableMore:
    def test_http_500_retryable(self):
        from common.exceptions import is_retryable_error, HTTPStatusError
        e = HTTPStatusError("url", 500, "err")
        assert is_retryable_error(e) is True

    def test_http_404_not_retryable(self):
        from common.exceptions import is_retryable_error, HTTPStatusError
        e = HTTPStatusError("url", 404, "err")
        assert is_retryable_error(e) is False

    def test_config_not_retryable(self):
        from common.exceptions import is_retryable_error, ConfigurationError
        assert is_retryable_error(ConfigurationError("msg")) is False
