"""
公共工具包：HTTP 请求、字段映射、工具函数、熔断器、数据源抽象。

包结构:
- common/__init__.py   # 主模块（re-export + 熔断器/数据源抽象）
- common/cache.py      # 磁盘缓存（v1.3.1 起从 data.cache 迁入）
- common/http.py       # HTTP 客户端
- common/parsers.py    # 字段映射与解析
- common/utils.py      # 工具函数
- common/exceptions/   # 统一异常类
- common/validators.py # 输入验证器
"""
import json
import threading
import time
from abc import ABC, abstractmethod
from enum import Enum

# ---------- 子模块导入 ----------

# 统一异常类
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

# HTTP 客户端
from common.http import (
    USER_AGENTS,
    http_get,
    http_get_with_headers,
    decode_gbk,
)

# 字段映射与解析
from common.parsers import (
    TENCENT_FIELDS,
    parse_tencent_line,
    SINA_QUOTE_URL,
    parse_sina_quote_line,
    EAST_MONEY_FIELDS,
)

# 工具函数
from common.utils import (
    PACKAGE_ROOT,
    DATA_DIR,
    split_codes,
    plain_code,
    infer_exchange,
    normalize_quote_code,
    normalize_finance_code,
    to_secid,
    board_type,
    is_etf,
    batchify,
    to_float,
    to_int,
    clamp,
    normalize_volume,
    normalize_amount,
    err,
    parallel_map,
)

# 输入验证器
from common.validators import (
    validate_code,
    normalize_code,
    validate_codes,
    validate_date,
    validate_date_range,
    validate_positive,
    validate_in_range,
)

# 缓存（v1.3.1：从此模块向上依赖，杜绝 common ↔ data 循环）
from common import cache
from common.cache import (
    CACHE_DIR,
    cache_get,
    cache_set,
    cache_cleanup,
    cache_key,
    cache_key_for_stock,
)

# 向后兼容别名
DataSourceUnavailableError = NetworkError
DataParseError = ParseError


# ---------- 带缓存的 HTTP 包装 ----------

def http_get_cached(url: str, timeout: int = 10, ttl: int = 21600) -> bytes:
    """带缓存的 HTTP GET。先读缓存，未命中则请求并写入缓存。"""
    key = cache.cache_key(url)
    cached = cache.get(key, ttl)
    if cached is not None:
        return cached
    data = http_get(url, timeout)
    cache.set(key, data)
    return data


def http_get_cached_keyed(url: str, key: str, timeout: int = 10, ttl: int = 21600) -> bytes:
    """带语义缓存键的 HTTP GET。"""
    cached = cache.get(key, ttl)
    if cached is not None:
        return cached
    data = http_get(url, timeout)
    cache.set(key, data)
    return data


# ---------- 熔断器 ----------

class CircuitState(Enum):
    CLOSED = "closed"        # 正常
    OPEN = "open"            # 熔断
    HALF_OPEN = "half_open"  # 试探


class CircuitBreaker:
    """线程安全的熔断器：连续失败 N 次后熔断，超时后半开试探。"""

    def __init__(self, name: str, failure_threshold: int = 5,
                 recovery_timeout: int = 60, half_open_max: int = 3):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max

        self._lock = threading.Lock()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.half_open_success = 0

    def can_execute(self) -> bool:
        """判断是否允许请求（线程安全）。"""
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_success = 0
                    return True
                return False
            if self.state == CircuitState.HALF_OPEN:
                return True
            return False

    def record_success(self):
        """记录成功（线程安全）。"""
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.half_open_success += 1
                if self.half_open_success >= self.half_open_max:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
            elif self.state == CircuitState.CLOSED:
                self.failure_count = 0

    def record_failure(self):
        """记录失败（线程安全）。"""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN

    def reset(self):
        """重置熔断器（线程安全）。"""
        with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.last_failure_time = 0


# 全局熔断器实例（线程安全）
_circuit_breakers = {}
_circuit_breakers_lock = threading.Lock()


def get_circuit_breaker(name: str, **kwargs) -> CircuitBreaker:
    """获取或创建熔断器实例（线程安全）。"""
    with _circuit_breakers_lock:
        if name not in _circuit_breakers:
            _circuit_breakers[name] = CircuitBreaker(name, **kwargs)
        return _circuit_breakers[name]


# ---------- 数据源抽象基类 ----------

class BaseFetcher(ABC):
    """数据源抽象基类。"""

    def __init__(self, name: str, priority: int = 0):
        self.name = name
        self.priority = priority
        self.circuit_breaker = get_circuit_breaker(name)

    @abstractmethod
    def fetch(self, code: str, **kwargs) -> dict | list | None:
        """获取数据。返回 None 表示失败。"""
        pass

    def is_available(self) -> bool:
        """检查数据源是否可用（熔断器状态）。"""
        return self.circuit_breaker.can_execute()

    def on_success(self):
        """记录成功。"""
        self.circuit_breaker.record_success()

    def on_failure(self):
        """记录失败。"""
        self.circuit_breaker.record_failure()


class DataFetcherManager:
    """数据源策略管理器：按优先级尝试，自动故障切换。"""

    def __init__(self, fetchers: list):
        self.fetchers = sorted(fetchers, key=lambda f: f.priority, reverse=True)

    def fetch(self, code: str, **kwargs) -> dict | list | None:
        """按优先级尝试各数据源。"""
        last_error = None
        for fetcher in self.fetchers:
            if not fetcher.is_available():
                continue
            try:
                result = fetcher.fetch(code, **kwargs)
                if result is not None:
                    fetcher.on_success()
                    return result
                fetcher.on_failure()
            except RateLimitError:
                fetcher.on_failure()
                raise  # 限流直接抛出
            except Exception as e:
                fetcher.on_failure()
                last_error = e
                continue
        return None

    def fetch_with_fallback(self, code: str, fallback=None, **kwargs):
        """带默认值的获取。"""
        result = self.fetch(code, **kwargs)
        return result if result is not None else fallback

    def fetch_with_cache_fallback(self, code: str, cache_prefix: str = None,
                                   cache_ttl: int = 21600, fallback=None, **kwargs):
        """带缓存降级的获取：优先实时数据 → 缓存数据 → 默认值。"""
        result = self.fetch(code, **kwargs)
        if result is not None:
            return result

        # 尝试从缓存降级
        if cache_prefix:
            key = cache.cache_key_for_stock(cache_prefix, code, **kwargs)
            cached = cache.get(key, cache_ttl)
            if cached is not None:
                try:
                    return json.loads(cached)
                except (json.JSONDecodeError, Exception):
                    pass

        return fallback


# ---------- 导出列表 ----------

__all__ = [
    # 基础设施
    "PACKAGE_ROOT", "DATA_DIR", "USER_AGENTS",
    "http_get", "http_get_with_headers", "http_get_cached", "http_get_cached_keyed",
    "decode_gbk",
    # 缓存（v1.3.1 起从 data.cache 迁入）
    "CACHE_DIR", "cache_get", "cache_set", "cache_cleanup",
    "cache_key", "cache_key_for_stock", "cache",
    # 字段映射与解析
    "TENCENT_FIELDS", "parse_tencent_line",
    "SINA_QUOTE_URL", "parse_sina_quote_line", "EAST_MONEY_FIELDS",
    # 工具函数
    "split_codes", "plain_code", "infer_exchange",
    "normalize_quote_code", "normalize_finance_code", "to_secid",
    "board_type", "is_etf", "batchify", "to_float", "to_int", "clamp",
    "normalize_volume", "normalize_amount",
    "err", "parallel_map",
    # 异常类
    "StockAnalyzerError", "DataError", "NetworkError", "RateLimitError",
    "ParseError", "DataUnavailableError", "BusinessError",
    "ValidationError", "StrategyError", "InsufficientDataError",
    "ConfigurationError", "format_error", "is_retryable_error",
    # 向后兼容别名
    "DataSourceUnavailableError", "DataParseError",
    # 熔断器
    "CircuitState", "CircuitBreaker", "get_circuit_breaker",
    # 数据源抽象
    "BaseFetcher", "DataFetcherManager",
    # 输入验证器
    "validate_code", "normalize_code", "validate_codes",
    "validate_date", "validate_date_range",
    "validate_positive", "validate_in_range",
]
