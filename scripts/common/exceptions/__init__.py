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

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.message = message
        self.details: dict[str, Any] = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }

    def __repr__(self) -> str:
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
        self.reason = reason
        super().__init__(
            f"网络请求失败: {reason}",
            {"url": url, "retry_count": retry_count, "reason": reason},
        )


class RateLimitError(NetworkError):
    """触发速率限制 (429)。"""

    def __init__(self, url: str, retry_after: int | None = None):
        self.retry_after = retry_after
        super().__init__(url, "429 Too Many Requests", 0)
        if retry_after is not None:
            self.message = f"触发速率限制，请 {retry_after} 秒后重试"
        else:
            self.message = "触发速率限制，请稍后重试"
        self.details["retry_after"] = retry_after


class ParseError(DataError):
    """数据解析失败。"""

    def __init__(self, raw_data: str, parser: str, reason: str):
        self.parser = parser
        self.raw_preview = raw_data[:200] if raw_data else ""
        super().__init__(
            f"数据解析失败 [{parser}]: {reason}",
            {"parser": parser, "data_preview": self.raw_preview},
        )


class HTTPStatusError(DataError):
    """HTTP 状态码错误（4xx 业务错误，非网络故障，不应触发熔断）。

    用于区分 404（数据不存在）等业务错误与网络故障：
    - 4xx（非 429）：业务错误，DataFetcherManager 应不熔断、换源。
    - 网络超时/连接失败：NetworkError，应熔断。
    """

    def __init__(self, url: str, status: int, body: str = ""):
        self.url = url
        self.status = status
        self.body = body[:200] if body else ""
        super().__init__(
            f"HTTP {status} for {url}",
            {"url": url, "status": status},
        )


class DataUnavailableError(DataError):
    """数据源不可用（连续失败）。"""

    def __init__(self, source: str, failures: int):
        self.source = source
        self.failures = failures
        super().__init__(
            f"数据源 [{source}] 不可用，已连续失败 {failures} 次",
            {"source": source, "failures": failures},
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
            {"field": field, "value": self.value_str, "constraint": constraint},
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
            {
                "data_type": data_type,
                "required": required,
                "actual": actual,
                "context": context,
            },
        )


class ConfigurationError(StockAnalyzerError):
    """配置错误。"""

    pass


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

# 用户友好的错误提示映射
USER_FRIENDLY_MESSAGES = {
    "NetworkError": {
        "default": "网络连接失败，请检查您的网络环境后重试",
        "timeout": "请求超时，数据源响应较慢，请稍后重试",
        "connection": "无法连接到数据服务器，请检查网络",
    },
    "RateLimitError": {"default": "请求过于频繁，请稍后再试"},
    "ParseError": {
        "default": "数据格式异常，技术团队已收到反馈",
        "empty": "暂无数据，请稍后重试",
    },
    "DataUnavailableError": {
        "default": "数据暂时不可用，已自动切换备用数据源",
        "all_failed": "所有数据源暂时不可用，请稍后再试",
    },
    "ValidationError": {
        "default": "输入信息有误，请检查后重新输入",
        "code": "股票代码格式不正确。支持三种输入：sh600989（带前缀）/ 600989（6位数字）/ 贵州茅台（中文名称）",
        "date": "日期格式有误，请使用如 2024-01-01 格式",
    },
    "InsufficientDataError": {
        "default": "分析数据不足，无法生成完整报告",
        "kline": "K线数据不足，请尝试获取更多历史数据",
        "finance": "财务数据缺失，可能影响分析准确性",
    },
    "ConfigurationError": {"default": "系统配置异常，请检查配置文件"},
}


def format_error(error: Exception, include_details: bool = False) -> str:
    """格式化异常为用户友好消息。

    Args:
        error: 异常对象
        include_details: 是否包含技术细节（调试模式）

    Returns:
        用户友好的错误消息
    """
    if isinstance(error, StockAnalyzerError):
        # 获取基础消息
        base_message = error.message

        # 根据异常类型获取用户友好消息
        friendly_msg = _get_friendly_message(error, base_message)

        # 如果是调试模式，附加技术细节
        if include_details and error.details:
            details_str = " | ".join(f"{k}: {v}" for k, v in error.details.items() if v)
            return f"{friendly_msg}\n📋 技术信息: {details_str}"

        return friendly_msg

    # 非项目异常的细化提示：常见内置异常给更具体消息
    import json

    if isinstance(error, json.JSONDecodeError):
        return "数据源返回了非 JSON 内容（可能是 HTML 错误页），已尝试备用数据源"
    if isinstance(error, KeyError):
        return f"数据字段缺失：{error.args[0] if error.args else '?'}（可能是数据源接口变更，请稍后重试）"
    if isinstance(error, TimeoutError):
        return "请求超时，已自动切换备用数据源"
    if isinstance(error, ConnectionError):
        return "网络连接失败，请检查网络后重试"
    return "发生了意外错误，请稍后重试。如果问题持续，请反馈给我们。"


def _get_friendly_message(error: StockAnalyzerError, base_message: str) -> str:
    """根据异常类型获取用户友好消息。"""
    error_class = error.__class__.__name__

    # 特殊处理 NetworkError 的不同原因
    if isinstance(error, NetworkError):
        reason = error.details.get("reason", "")
        if "timeout" in reason.lower():
            return USER_FRIENDLY_MESSAGES["NetworkError"]["timeout"]
        elif "refused" in reason.lower() or "connection" in reason.lower():
            return USER_FRIENDLY_MESSAGES["NetworkError"]["connection"]
        return USER_FRIENDLY_MESSAGES["NetworkError"]["default"]

    # ValidationError 的特殊处理
    if isinstance(error, ValidationError):
        field = error.details.get("field", "")
        if field in ("code", "stock_code"):
            return USER_FRIENDLY_MESSAGES["ValidationError"]["code"]
        elif field in ("date", "start_date", "end_date"):
            return USER_FRIENDLY_MESSAGES["ValidationError"]["date"]
        return USER_FRIENDLY_MESSAGES["ValidationError"]["default"]

    # InsufficientDataError 的特殊处理
    if isinstance(error, InsufficientDataError):
        data_type = error.details.get("data_type", "")
        if "kline" in data_type.lower() or "K线" in base_message:
            return USER_FRIENDLY_MESSAGES["InsufficientDataError"]["kline"]
        elif "finance" in data_type.lower() or "财务" in base_message:
            return USER_FRIENDLY_MESSAGES["InsufficientDataError"]["finance"]
        return USER_FRIENDLY_MESSAGES["InsufficientDataError"]["default"]

    # 其他异常类型
    if error_class in USER_FRIENDLY_MESSAGES:
        return USER_FRIENDLY_MESSAGES[error_class]["default"]

    return base_message


def is_retryable_error(error: Exception) -> bool:
    """判断错误是否可重试。"""
    if isinstance(error, RateLimitError):
        return True
    if isinstance(error, NetworkError):
        return True
    # 5xx 服务端错误（502/503/504 等）通常为临时故障，应可重试
    if isinstance(error, HTTPStatusError) and error.status >= 500:
        return True
    return False


__all__ = [
    "StockAnalyzerError",
    "DataError",
    "NetworkError",
    "RateLimitError",
    "ParseError",
    "HTTPStatusError",
    "DataUnavailableError",
    "BusinessError",
    "ValidationError",
    "StrategyError",
    "InsufficientDataError",
    "ConfigurationError",
    "format_error",
    "is_retryable_error",
    "USER_FRIENDLY_MESSAGES",
]
