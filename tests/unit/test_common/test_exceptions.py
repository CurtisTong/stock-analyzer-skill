"""
统一异常类测试。
"""
import pytest
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from common.exceptions import (
    StockAnalyzerError,
    DataError,
    NetworkError,
    RateLimitError,
    ParseError,
    DataUnavailableError,
    BusinessError,
    ValidationError,
    StrategyError,
    InsufficientDataError,
    ConfigurationError,
    format_error,
    is_retryable_error,
)


class TestStockAnalyzerError:
    """基础异常测试。"""

    def test_basic_error(self):
        """测试基础异常创建。"""
        err = StockAnalyzerError("测试错误", {"key": "value"})
        assert err.message == "测试错误"
        assert err.details == {"key": "value"}
        assert err.to_dict()["error_type"] == "StockAnalyzerError"

    def test_repr(self):
        """测试异常表示。"""
        err = StockAnalyzerError("测试错误")
        assert "StockAnalyzerError" in repr(err)


class TestDataError:
    """数据层异常测试。"""

    def test_network_error(self):
        """测试网络错误。"""
        err = NetworkError("http://example.com", "Connection refused", 2)
        assert err.url == "http://example.com"
        assert err.retry_count == 2
        assert "NetworkError" in err.to_dict()["error_type"]

    def test_rate_limit_error(self):
        """测试限流错误。"""
        err = RateLimitError("http://example.com", 60)
        assert err.retry_after == 60
        assert is_retryable_error(err)

    def test_parse_error(self):
        """测试解析错误。"""
        raw = "invalid json data"
        err = ParseError(raw, "JSONParser", "Expecting value")
        assert err.parser == "JSONParser"
        # 仅保存前200字符
        assert len(err.raw_preview) <= 200

    def test_data_unavailable_error(self):
        """测试数据不可用错误。"""
        err = DataUnavailableError("tencent_quote", 5)
        assert err.source == "tencent_quote"
        assert err.failures == 5


class TestBusinessError:
    """业务层异常测试。"""

    def test_validation_error(self):
        """测试输入校验错误。"""
        err = ValidationError("code", "invalid", "必须为6位数字")
        assert err.field == "code"
        assert err.value_str == "invalid"

    def test_validation_error_value_truncate(self):
        """测试长值截断。"""
        long_value = "a" * 300
        err = ValidationError("code", long_value, "格式错误")
        assert len(err.value_str) <= 100

    def test_insufficient_data_error(self):
        """测试数据不足错误。"""
        err = InsufficientDataError("K线", 30, 10, "sh600989")
        assert err.data_type == "K线"
        assert err.required == 30
        assert err.actual == 10

    def test_strategy_error(self):
        """测试策略错误。"""
        err = StrategyError("策略不存在")
        assert "策略不存在" in err.message


class TestHelperFunctions:
    """辅助函数测试。"""

    def test_format_error_custom(self):
        """测试自定义异常格式化。"""
        err = ValidationError("code", "abc", "格式错误")
        assert format_error(err) == "字段 code 校验失败: 格式错误"

    def test_format_error_generic(self):
        """测试通用异常格式化。"""
        err = ValueError("Some error")
        assert format_error(err) == "未知错误: Some error"

    def test_is_retryable_error(self):
        """测试可重试错误判断。"""
        assert is_retryable_error(RateLimitError("url", 60)) is True
        assert is_retryable_error(NetworkError("url", "err", 0)) is True
        assert is_retryable_error(ValidationError("f", "v", "c")) is False
        assert is_retryable_error(ValueError("test")) is False
