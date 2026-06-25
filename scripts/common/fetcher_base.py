"""数据源抽象基类和管理器。

包含 BaseFetcher（数据源抽象）、DataFetcherManager（优先级故障切换）、
NOT_HANDLED 哨兵（标记不处理的代码）。
"""

import re
from abc import ABC, abstractmethod

from common.circuit_breaker import get_circuit_breaker
from common.exceptions import RateLimitError

# 股票代码安全白名单：允许字母、数字、下划线、点号、冒号、脱字符（美股指数如 us:^gspc）
_SAFE_CODE_PATTERN = re.compile(r"^[a-zA-Z0-9_.:^]+$")

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
        self.circuit_breaker = get_circuit_breaker(name, **self._load_cb_config())

    @staticmethod
    def _load_cb_config() -> dict[str, int]:
        """从 data_source.yaml 加载熔断器配置。"""
        try:
            from config.loader import ConfigLoader

            cb = ConfigLoader.load("data_source.yaml").get("circuit_breaker", {})
            return {
                "failure_threshold": cb.get("failure_threshold", 5),
                "recovery_timeout": cb.get("recovery_timeout", 60),
                "half_open_max": cb.get("half_open_max", 3),
            }
        except Exception:
            return {}

    @abstractmethod
    def fetch(
        self, code: str, **kwargs: object
    ) -> dict[str, object] | list[object] | None:
        """获取数据。

        返回值语义：
        - 非 None: 成功获取数据
        - None: 数据不存在（如新股无财务数据），不触发熔断
        - NOT_HANDLED: 不处理该类代码，跳过
        - 抛出异常: 获取失败，触发熔断
        """
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
        """按优先级尝试各数据源。

        返回 None 表示所有源都无数据（非失败）。
        仅在异常时触发熔断，None 返回不触发。
        """
        if not code or not _SAFE_CODE_PATTERN.match(str(code)):
            return None
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
                # None 表示数据不存在，不触发熔断，尝试下一个源
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
