"""
公共工具包：HTTP 请求、字段映射、工具函数、熔断器、数据源抽象。

核心子模块（fetcher_base/circuit_breaker/exceptions/validators）在 import common 时加载；
可选子模块（parsers/exporters）通过 PEP 562 __getattr__ 延迟加载。
"""

# ---------- 从子模块 re-export（零破坏迁移） ----------
from common.circuit_breaker import (
    CircuitState,
    CircuitBreaker,
    get_circuit_breaker,
)
from common.fetcher_base import NOT_HANDLED, BaseFetcher, DataFetcherManager, fetch_with_breaker
from common.lazy_registry import LazyFetcherRegistry

# ---------- 异常类（零副作用，顶层导入） ----------

from common.exceptions import (
    StockAnalyzerError,
    DataError,
    NetworkError,
    RateLimitError,
    ParseError,
    HTTPStatusError,
    DataUnavailableError,
    BusinessError,
    ValidationError,
    StrategyError,
    InsufficientDataError,
    ConfigurationError,
    format_error,
    is_retryable_error,
)

# 向后兼容别名
DataSourceUnavailableError = NetworkError
DataParseError = ParseError


# ---------- 懒加载映射 ----------

_LAZY_IMPORTS = {
    # HTTP 客户端
    "USER_AGENTS": ("common.http", "USER_AGENTS"),
    "http_get": ("common.http", "http_get"),
    "http_get_with_headers": ("common.http", "http_get_with_headers"),
    "decode_gbk": ("common.http", "decode_gbk"),
    # 字段映射
    "TENCENT_FIELDS": ("common.parsers", "TENCENT_FIELDS"),
    "parse_tencent_line": ("common.parsers", "parse_tencent_line"),
    "SINA_QUOTE_URL": ("common.parsers", "SINA_QUOTE_URL"),
    "parse_sina_quote_line": ("common.parsers", "parse_sina_quote_line"),
    "EAST_MONEY_FIELDS": ("common.parsers", "EAST_MONEY_FIELDS"),
    # 工具函数
    "PACKAGE_ROOT": ("common.utils", "PACKAGE_ROOT"),
    "DATA_DIR": ("common.utils", "DATA_DIR"),
    "split_codes": ("common.utils", "split_codes"),
    "plain_code": ("common.utils", "plain_code"),
    "infer_exchange": ("common.utils", "infer_exchange"),
    "normalize_quote_code": ("common.utils", "normalize_quote_code"),
    "normalize_finance_code": ("common.utils", "normalize_finance_code"),
    "to_secid": ("common.utils", "to_secid"),
    "board_type": ("common.utils", "board_type"),
    "board_limit_pct": ("common.utils", "board_limit_pct"),
    "board_exact_limit_pct": ("common.utils", "board_exact_limit_pct"),
    "is_etf": ("common.utils", "is_etf"),
    "batchify": ("common.utils", "batchify"),
    "to_float": ("common.utils", "to_float"),
    "to_int": ("common.utils", "to_int"),
    "clamp": ("common.utils", "clamp"),
    "normalize_volume": ("common.utils", "normalize_volume"),
    "normalize_amount": ("common.utils", "normalize_amount"),
    "compute_volume_ratio": ("common.utils", "compute_volume_ratio"),
    "compute_optimal_workers": ("common.utils", "compute_optimal_workers"),
    "err": ("common.utils", "err"),
    "parallel_map": ("common.utils", "parallel_map"),
    "parallel_fetch_dict": ("common.utils", "parallel_fetch_dict"),
    "get_shared_executor": ("common.utils", "get_shared_executor"),
    # 验证器
    "validate_code": ("common.validators", "validate_code"),
    "normalize_code": ("common.validators", "normalize_code"),
    "validate_codes": ("common.validators", "validate_codes"),
    "validate_date": ("common.validators", "validate_date"),
    "validate_date_range": ("common.validators", "validate_date_range"),
    "validate_positive": ("common.validators", "validate_positive"),
    "validate_in_range": ("common.validators", "validate_in_range"),
    # 缓存
    "cache": ("common.cache", None),
    "CACHE_DIR": ("common.cache", "CACHE_DIR"),
    "cache_get": ("common.cache", "cache_get"),
    "cache_set": ("common.cache", "cache_set"),
    "cache_put": ("common.cache", "put"),
    "cache_cleanup": ("common.cache", "cache_cleanup"),
    "cache_key": ("common.cache", "cache_key"),
    "cache_key_for_stock": ("common.cache", "cache_key_for_stock"),
    # 前缀工具
    "strip_prefix": ("common.utils", "strip_prefix"),
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        import importlib

        mod = importlib.import_module(module_path)
        if attr is None:
            val = mod
        else:
            val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module 'common' has no attribute {name!r}")


# ---------- 带缓存的 HTTP 包装 ----------


def http_get_cached(
    url: str, timeout: int = 10, ttl: int = 21600, key: str = None
) -> bytes:
    """带缓存的 HTTP GET。先读缓存，未命中则请求并写入缓存。

    Args:
        url: 请求 URL
        timeout: 超时秒数
        ttl: 缓存有效期秒数
        key: 自定义缓存键，为 None 时用 cache_key(url) 自动生成
    """
    from common import cache, http_get

    cache_key_ = key if key is not None else cache.cache_key(url)
    cached = cache.get(cache_key_, ttl)
    if cached is not None:
        return cached
    data = http_get(url, timeout)
    cache.put(cache_key_, data)
    return data


def http_get_cached_keyed(
    url: str, key: str, timeout: int = 10, ttl: int = 21600
) -> bytes:
    """带语义缓存键的 HTTP GET（向后兼容别名，委托 http_get_cached）。"""
    return http_get_cached(url, timeout=timeout, ttl=ttl, key=key)


# ---------- 导出列表 ----------

__all__ = [
    # 基础设施
    "PACKAGE_ROOT",
    "DATA_DIR",
    "USER_AGENTS",
    "http_get",
    "http_get_with_headers",
    "http_get_cached",
    "http_get_cached_keyed",
    "decode_gbk",
    # 缓存
    "CACHE_DIR",
    "cache_get",
    "cache_set",
    "cache_put",
    "cache_cleanup",
    "cache_key",
    "cache_key_for_stock",
    "strip_prefix",
    "cache",
    # 字段映射
    "TENCENT_FIELDS",
    "parse_tencent_line",
    "SINA_QUOTE_URL",
    "parse_sina_quote_line",
    "EAST_MONEY_FIELDS",
    # 工具函数
    "split_codes",
    "plain_code",
    "infer_exchange",
    "normalize_quote_code",
    "normalize_finance_code",
    "to_secid",
    "board_type",
    "board_limit_pct",
    "board_exact_limit_pct",
    "is_etf",
    "batchify",
    "to_float",
    "to_int",
    "clamp",
    "normalize_volume",
    "normalize_amount",
    "compute_volume_ratio",
    "compute_optimal_workers",
    "err",
    "parallel_map",
    "parallel_fetch_dict",
    "get_shared_executor",
    # 异常类
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
    # 向后兼容别名
    "DataSourceUnavailableError",
    "DataParseError",
    # 熔断器
    "CircuitState",
    "CircuitBreaker",
    "get_circuit_breaker",
    # 数据源抽象
    "NOT_HANDLED",
    "BaseFetcher",
    "DataFetcherManager",
    "fetch_with_breaker",
    "LazyFetcherRegistry",
    # 输入验证器
    "validate_code",
    "normalize_code",
    "validate_codes",
    "validate_date",
    "validate_date_range",
    "validate_positive",
    "validate_in_range",
]
