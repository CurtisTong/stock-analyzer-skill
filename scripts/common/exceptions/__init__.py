"""
统一异常类定义。

异常层次结构:
- StockAnalyzerError (基础)
  ├── DataError (数据层)
  │   ├── NetworkError
  │   ├── RateLimitError
  │   ├── ParseError
  │   └── DataUnavailableError
  │
  └── BusinessError (业务层)
      ├── ValidationError
      ├── StrategyError
      └── InsufficientDataError
"""
from typing import Any


class StockAnalyzerError(Exception):
    """项目基础异常类。"""

    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }

    def __repr__(self):
        return f"{self.__class__.__name__}({self.message})"


# ═══════════════════════════════════════════════════════════════
# 数据层异常
# ═══════════════════════════════════════════════════════════════

class DataError(StockAnalyzerError):
    """数据层基类异常。"""
    pass


class NetworkError(DataError):
    """网络请求失败。"""

    def __init__(self, url: str, reason: str, retry_count: int = 0):
        self.url = url
        self.retry_count = retry_count
        super().__init__(
            f"网络请求失败: {reason}",
            {"url": url, "retry_count": retry_count}
        )


class RateLimitError(NetworkError):
    """触发速率限制 (429)。"""

    def __init__(self, url: str, retry_after: int = None):
        self.retry_after = retry_after
        super().__init__(url, "429 Too Many Requests", 0)
        self.message = f"触发速率限制，请 {retry_after} 秒后重试"


class ParseError(DataError):
    """数据解析失败。"""

    def __init__(self, raw_data: str, parser: str, reason: str):
        self.parser = parser
        self.raw_preview = raw_data[:200] if raw_data else ""
        super().__init__(
            f"数据解析失败 [{parser}]: {reason}",
            {"parser": parser, "data_preview": self.raw_preview}
        )


class DataUnavailableError(DataError):
    """数据源不可用（连续失败）。"""

    def __init__(self, source: str, failures: int):
        self.source = source
        self.failures = failures
        super().__init__(
            f"数据源 [{source}] 不可用，已连续失败 {failures} 次",
            {"source": source, "failures": failures}
        )


# ═══════════════════════════════════════════════════════════════
# 业务层异常
# ═══════════════════════════════════════════════════════════════

class BusinessError(StockAnalyzerError):
    """业务层基类异常。"""
    pass


class ValidationError(BusinessError):
    """输入校验失败。"""

    def __init__(self, field: str, value: Any, constraint: str):
        self.field = field
        self.value_str = str(value)[:100] if value is not None else None
        super().__init__(
            f"字段 {field} 校验失败: {constraint}",
            {"field": field, "value": self.value_str, "constraint": constraint}
        )


class StrategyError(BusinessError):
    """策略执行错误。"""
    pass


class InsufficientDataError(BusinessError):
    """数据不足，无法执行分析。"""

    def __init__(self, data_type: str, required: int, actual: int, context: str = ""):
        self.data_type = data_type
        self.required = required
        self.actual = actual
        context_info = f" [{context}]" if context else ""
        super().__init__(
            f"{data_type}数据不足{context_info}: 需要 {required} 条，实际 {actual} 条",
            {"data_type": data_type, "required": required, "actual": actual, "context": context}
        )


class ConfigurationError(StockAnalyzerError):
    """配置错误。"""
    pass


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def format_error(error: Exception) -> str:
    """格式化异常为用户友好消息。"""
    if isinstance(error, StockAnalyzerError):
        return error.message
    return f"未知错误: {str(error)}"


def is_retryable_error(error: Exception) -> bool:
    """判断错误是否可重试。"""
    if isinstance(error, RateLimitError):
        return True
    if isinstance(error, NetworkError):
        return True
    return False


__all__ = [
    "StockAnalyzerError",
    "DataError",
    "NetworkError",
    "RateLimitError",
    "ParseError",
    "DataUnavailableError",
    "BusinessError",
    "ValidationError",
    "StrategyError",
    "InsufficientDataError",
    "ConfigurationError",
    "format_error",
    "is_retryable_error",
]
