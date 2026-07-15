import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestExceptionMessages:
    def test_network_error_message(self):
        from common.exceptions import NetworkError

        e = NetworkError("http://test.com", "timeout")
        msg = str(e)
        assert "timeout" in msg or "test.com" in msg

    def test_rate_limit_error_message(self):
        from common.exceptions import RateLimitError

        e = RateLimitError("http://test.com", retry_after=120)
        msg = str(e)
        assert isinstance(msg, str)

    def test_parse_error(self):
        from common.exceptions import ParseError

        e = ParseError("url", "content", "parse failed")
        assert isinstance(str(e), str)

    def test_data_unavailable(self):
        from common.exceptions import DataUnavailableError

        e = DataUnavailableError("url", "msg")
        assert isinstance(e, Exception)

    def test_business_error(self):
        from common.exceptions import BusinessError

        e = BusinessError("msg")
        assert isinstance(e, Exception)

    def test_validation_error(self):
        from common.exceptions import ValidationError

        e = ValidationError("field", "value", "invalid")
        assert isinstance(e, Exception)

    def test_strategy_error(self):
        from common.exceptions import StrategyError

        e = StrategyError("msg")
        assert isinstance(e, Exception)

    def test_configuration_error(self):
        from common.exceptions import ConfigurationError

        e = ConfigurationError("msg")
        assert isinstance(e, Exception)


class TestIsRetryable:
    def test_network_retryable(self):
        from common.exceptions import is_retryable_error, NetworkError

        assert is_retryable_error(NetworkError("url", "err")) is True

    def test_parse_not_retryable(self):
        from common.exceptions import is_retryable_error, ParseError

        assert is_retryable_error(ParseError("url", "content", "err")) is False

    def test_business_not_retryable(self):
        from common.exceptions import is_retryable_error, BusinessError

        assert is_retryable_error(BusinessError("msg")) is False

    def test_generic_not_retryable(self):
        from common.exceptions import is_retryable_error

        assert is_retryable_error(ValueError("err")) is False
