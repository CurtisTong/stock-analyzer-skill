"""数据源抽象基类和管理器。

包含 BaseFetcher（数据源抽象）、DataFetcherManager（优先级故障切换）、
NOT_HANDLED 哨兵（标记不处理的代码）。
"""

import logging
import re
from abc import ABC, abstractmethod

from common.circuit_breaker import get_circuit_breaker

logger = logging.getLogger(__name__)
from common.exceptions import RateLimitError, HTTPStatusError

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

    _cb_config_cache: dict[str, int] | None = None  # 类级缓存，避免每次实例化读 YAML

    def __init__(self, name: str, priority: int = 0, provider: str | None = None):
        self.name = name
        # 显式 provider 优先；否则从 name 推断（取最后一个 _ 前的段落，
        # 这样 "northbound_flow_eastmoney" -> "eastmoney"，"tencent_quote" -> "tencent"）
        if provider is not None:
            self.provider = provider
        elif "_" in name:
            # 尝试取最后一段作为 provider（如 xxx_eastmoney -> eastmoney），
            # 兼容旧格式 xxx_tencent -> tencent
            parts = name.split("_")
            # 如果最后一段是已知 provider，用它；否则用第一段
            _KNOWN_PROVIDERS = {
                "tencent", "eastmoney", "sina", "xueqiu", "ths", "efinance",
                "akshare", "tushare", "pytdx", "baostock", "yfinance",
            }
            self.provider = parts[-1] if parts[-1] in _KNOWN_PROVIDERS else parts[0]
        else:
            self.provider = name
        self.priority = priority
        self.enabled = True  # 可通过 data_source.yaml 的 enabled 字段覆盖
        # P0-03: timeout/retry 从 data_source.yaml 读取（_apply_source_config 覆盖），
        # 默认值与 http_get 内置默认一致，保证未配置时行为不变。
        self.timeout: int = 10
        self.retry: int = 3
        self.circuit_breaker = get_circuit_breaker(name, **self._load_cb_config())

    @classmethod
    def _load_cb_config(cls) -> dict[str, int]:
        """从 data_source.yaml 加载熔断器配置（类级缓存）。"""
        if cls._cb_config_cache is not None:
            return cls._cb_config_cache
        try:
            from config.loader import ConfigLoader

            cb = ConfigLoader.load("data_source.yaml").get("circuit_breaker", {})
            cls._cb_config_cache = {
                "failure_threshold": cb.get("failure_threshold", 5),
                "recovery_timeout": cb.get("recovery_timeout", 60),
                "half_open_max": cb.get("half_open_max", 3),
            }
        except Exception as e:
            logger.debug("加载熔断器配置失败，使用默认值: %s", e)
            cls._cb_config_cache = {}
        return cls._cb_config_cache

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
        """检查 fetcher 是否可用（启用 + 熔断器未打开）。

        注意（T16）：can_execute() 与 record_*() 分两步调用存在 TOCTOU 竞态--
        多线程下可能在 can_execute() 返回 True 后、实际 fetch 前另一线程触发熔断。
        本项目采用"乐观并发"策略：容忍少量竞态（最多多放行 1-2 次请求），
        因 fetch 本身有超时保护，不会导致雪崩。如需严格原子性可合并为 try_fetch() 原子操作。
        """
        return self.enabled and self.circuit_breaker.can_execute()

    def on_success(self) -> None:
        self.circuit_breaker.record_success()

    def on_failure(self) -> None:
        self.circuit_breaker.record_failure()


def fetch_with_breaker(fetcher: BaseFetcher, *args, **kwargs):
    """带熔断器保护的 fetch 调用。

    用于不走 DataFetcherManager 的数据域（chip/event/flow/lhb，
    返回不同子类型数据故不走 manager 故障转移）。

    - fetcher 不可用（熔断器开启）→ 返回 None
    - fetch 成功 → 记录成功，返回结果
    - fetch 返回 None/NOT_HANDLED → 不记录成功/失败（数据不存在，非故障）
    - fetch 抛异常 → 记录失败，返回 None

    Returns:
        fetcher.fetch() 的返回值，或熔断/异常时 None
    """
    # 与 DataFetcherManager.fetch 保持一致：code 白名单防御
    # chip/event/flow/lhb 域不走 manager 但仍可能收到外部输入
    if args and not _SAFE_CODE_PATTERN.match(str(args[0])):
        return None
    if not fetcher.is_available():
        return None
    try:
        result = fetcher.fetch(*args, **kwargs)
    except Exception as e:
        logger.debug(
            "fetch_with_breaker %s 异常: %s", fetcher.__class__.__name__, e
        )
        fetcher.on_failure()
        return None
    if result is not None and result is not NOT_HANDLED:
        fetcher.on_success()
    return result


class DataFetcherManager:
    """数据源策略管理器：按优先级尝试，自动故障切换。"""

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
                if "enabled" in cfg:
                    fetcher.enabled = bool(cfg["enabled"])
                # P0-03: 读取 timeout/retry，使 data_source.yaml 配置生效
                if "timeout" in cfg:
                    fetcher.timeout = int(cfg["timeout"])
                if "retry" in cfg:
                    fetcher.retry = int(cfg["retry"])

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
            except RateLimitError as e:
                # 429 限速：记录失败并尝试下一个源，而非直接 raise。
                # 限速通常是针对特定 API key 的限制，其他源未必受限。
                fetcher.on_failure()
                self._last_error = e
                continue
            except HTTPStatusError as e:
                # P2-H2(common): 4xx 业务错误（如 404 数据不存在）不计入熔断，
                # 直接换下一个源尝试，避免误熔断数据源
                self._last_error = e
                continue
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
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning("缓存数据损坏(key=%s)，回退到实时获取: %s", key, e)
        return fallback
