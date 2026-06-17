"""
公共工具包：HTTP 请求、字段映射、工具函数、熔断器、数据源抽象。

采用 PEP 562 __getattr__ 懒加载，import common 时不触发子模块加载。
"""

import threading
import time
from abc import ABC, abstractmethod
from enum import Enum

# ---------- 异常类（零副作用，顶层导入） ----------

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


def http_get_cached(url: str, timeout: int = 10, ttl: int = 21600) -> bytes:
    """带缓存的 HTTP GET。先读缓存，未命中则请求并写入缓存。"""
    from common import cache, http_get

    key = cache.cache_key(url)
    cached = cache.get(key, ttl)
    if cached is not None:
        return cached
    data = http_get(url, timeout)
    cache.put(key, data)
    return data


def http_get_cached_keyed(
    url: str, key: str, timeout: int = 10, ttl: int = 21600
) -> bytes:
    """带语义缓存键的 HTTP GET。"""
    from common import cache, http_get

    cached = cache.get(key, ttl)
    if cached is not None:
        return cached
    data = http_get(url, timeout)
    cache.put(key, data)
    return data


# ---------- 熔断器（零外部依赖，保留顶层） ----------


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """线程安全的熔断器：连续失败 N 次后熔断，超时后半开试探。"""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max: int = 3,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max

        self._lock = threading.Lock()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: float = 0.0
        self.half_open_success = 0
        self._half_open_token = False

    def can_execute(self) -> bool:
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_success = 0
                    self._half_open_token = False
                    return True
                return False
            if self.state == CircuitState.HALF_OPEN:
                if self._half_open_token:
                    self._half_open_token = False
                    return True
                return False
            return False

    def record_success(self) -> None:
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self._half_open_token = False
            elif self.state == CircuitState.CLOSED:
                self.failure_count = 0

    def record_failure(self) -> None:
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            self._half_open_token = False
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN

    def reset(self) -> None:
        with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.last_failure_time = 0
            self._half_open_token = False


_circuit_breakers: dict[str, CircuitBreaker] = {}
_circuit_breakers_lock = threading.Lock()


def get_circuit_breaker(name: str, **kwargs: int) -> CircuitBreaker:
    with _circuit_breakers_lock:
        if name not in _circuit_breakers:
            _circuit_breakers[name] = CircuitBreaker(name, **kwargs)
        return _circuit_breakers[name]


# ---------- NOT_HANDLED 哨兵（可序列化） ----------


def _get_not_handled():
    """pickle 反序列化用：返回 NOT_HANDLED 单例。"""
    return NOT_HANDLED


class _NotHandled:
    """可序列化的 NOT_HANDLED 哨兵。"""

    def __repr__(self):
        return "NOT_HANDLED"

    def __reduce__(self):
        return (_get_not_handled, ())

    def __eq__(self, other):
        return isinstance(other, _NotHandled)

    def __hash__(self):
        return hash("_NOT_HANDLED_")


NOT_HANDLED = _NotHandled()


# ---------- 数据源抽象基类 ----------


class BaseFetcher(ABC):
    """数据源抽象基类。"""

    def __init__(self, name: str, priority: int = 0):
        self.name = name
        self.provider = name.split("_")[0]
        self.priority = priority
        self.circuit_breaker = get_circuit_breaker(name)

    @abstractmethod
    def fetch(
        self, code: str, **kwargs: object
    ) -> dict[str, object] | list[object] | None:
        """获取数据。返回 None 表示失败，返回 NOT_HANDLED 表示不处理该类代码。"""
        pass

    def is_available(self) -> bool:
        return self.circuit_breaker.can_execute()

    def on_success(self) -> None:
        self.circuit_breaker.record_success()

    def on_failure(self) -> None:
        self.circuit_breaker.record_failure()


class DataFetcherManager:
    """数据源策略管理器：按优先级尝试，自动故障切换。"""

    _DOMAIN_SECTION_MAP = {
        "quote": "quote_sources",
        "kline": "kline_sources",
        "finance": "finance_sources",
    }

    def __init__(
        self,
        fetchers: list[BaseFetcher],
        source_config: dict[str, object] | None = None,
    ):
        if source_config:
            self._apply_source_config(fetchers, source_config)
        self.fetchers = sorted(fetchers, key=lambda f: f.priority, reverse=True)
        self._last_error: Exception | None = None

    @property
    def last_error(self) -> Exception | None:
        """最后一次 fetch 失败的异常。"""
        return self._last_error

    @staticmethod
    def _apply_source_config(
        fetchers: list[BaseFetcher], source_config: dict[str, object]
    ) -> None:
        for fetcher in fetchers:
            cfg = source_config.get(fetcher.provider)
            if cfg and isinstance(cfg, dict):
                fetcher.priority = cfg.get("priority", fetcher.priority)

    def fetch(
        self, code: str, **kwargs: object
    ) -> dict[str, object] | list[object] | None:
        """按优先级尝试各数据源。"""
        self._last_error = None
        for fetcher in self.fetchers:
            if not fetcher.is_available():
                continue
            try:
                result = fetcher.fetch(code, **kwargs)
                if result is NOT_HANDLED:
                    continue
                if result is not None:
                    fetcher.on_success()
                    return result
                fetcher.on_failure()
            except RateLimitError:
                fetcher.on_failure()
                raise
            except Exception as e:
                fetcher.on_failure()
                self._last_error = e
                continue
        return None

    def fetch_with_fallback(
        self, code: str, fallback: object = None, **kwargs: object
    ) -> object:
        result = self.fetch(code, **kwargs)
        return result if result is not None else fallback

    def fetch_with_cache_fallback(
        self,
        code: str,
        cache_prefix: str | None = None,
        cache_ttl: int = 21600,
        fallback: object = None,
        **kwargs: object,
    ) -> object:
        from common import cache

        result = self.fetch(code, **kwargs)
        if result is not None:
            return result
        if cache_prefix:
            key = cache.cache_key_for_stock(cache_prefix, code, **kwargs)
            cached = cache.get(key, cache_ttl)
            if cached is not None:
                try:
                    import json

                    return json.loads(cached)
                except (json.JSONDecodeError, Exception):
                    pass
        return fallback


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
    # 输入验证器
    "validate_code",
    "normalize_code",
    "validate_codes",
    "validate_date",
    "validate_date_range",
    "validate_positive",
    "validate_in_range",
]
