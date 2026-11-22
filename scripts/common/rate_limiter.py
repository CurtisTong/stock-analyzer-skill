"""全局限流器：按 provider 维度控制并发 + 429 指数退避。

(2026-07-21) 新增。
v1.16.0 (2026-07-28) Batch 2 修订：
- 新增 ``slot()`` 上下文管理器（强制 try/finally 释放信号量，
  解决  信号量泄漏风险）。
- 公开 API 保留 ``acquire()``/``release()`` 以兼容 ``fetcher_base.py`` 的
  现有调用点；新代码优先使用 ``slot()``。
2026-11-21 code review P1-3：退避 sleep 改为**拿槽前**执行，
interrupt 不再泄漏 permit，也不再持槽 sleep 压垮并发。
- 与 ``circuit_breaker`` 编排：``is_provider_disabled(provider)``
  作为 circuit breaker 的旁路检查（fetcher_base.py 可调用）。

设计：
- 每个 provider 独立 BoundedSemaphore，默认并发 8（来自 data_source.yaml.rate_limit.default_max_concurrent）
- 遇 429 时标记 _last_429[provider] = now()
- 下次 acquire() 时若 elapsed < 退避窗口（默认 2s），sleep 补足窗口
- 退避窗口随 429 次数累计（指数 backoff），单次 max 8s

线程安全：所有内部状态用 threading.Lock 保护。
"""

import logging
import threading
import time
from contextlib import contextmanager
from typing import Dict, Iterator
from common.exceptions.silent_fallback import log_silent_fallback

logger = logging.getLogger(__name__)

# 默认配置（可被 data_source.yaml.rate_limit 覆盖）
_DEFAULT_MAX_CONCURRENT = 8
_DEFAULT_BACKOFF_BASE = 1.0  # 首次 429 sleep 时长（秒）
_DEFAULT_BACKOFF_CAP = 8.0  # 单次最大 sleep（秒）
_DEFAULT_BACKOFF_WINDOW = 30.0  # 退避窗口（超过此时间重置）


class RateLimiter:
    """按 provider 维度的并发信号量 + 429 退避追踪。"""

    def __init__(
        self,
        max_concurrent: int = _DEFAULT_MAX_CONCURRENT,
        backoff_base: float = _DEFAULT_BACKOFF_BASE,
        backoff_cap: float = _DEFAULT_BACKOFF_CAP,
        backoff_window: float = _DEFAULT_BACKOFF_WINDOW,
    ):
        self.max_concurrent = max_concurrent
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.backoff_window = backoff_window

        self._semaphores: Dict[str, threading.BoundedSemaphore] = {}
        self._sem_lock = threading.Lock()
        # provider -> (last_429_time, consecutive_429_count)
        self._backoff_state: Dict[str, tuple] = {}
        self._backoff_lock = threading.Lock()

    def _get_semaphore(self, provider: str) -> threading.BoundedSemaphore:
        """懒创建 provider 对应的信号量。"""
        sem = self._semaphores.get(provider)
        if sem is not None:
            return sem
        with self._sem_lock:
            sem = self._semaphores.get(provider)
            if sem is None:
                sem = threading.BoundedSemaphore(self.max_concurrent)
                self._semaphores[provider] = sem
            return sem

    def _compute_backoff(self, consecutive_429: int) -> float:
        """计算退避时长：指数增长，cap 封顶。"""
        delay = self.backoff_base * (2 ** (consecutive_429 - 1))
        return min(delay, self.backoff_cap)

    def _backoff_delay(self, provider: str) -> float:
        """P1-3(3.1): 计算退避时长，但**不持有信号量**。

        退避状态读写仍在 _backoff_lock 内（原逻辑保留：窗口过期则重置计数），
        但返回的 sleep 时长由调用方在**拿槽之前**使用。这样即便 sleep 被
        KeyboardInterrupt 打断，也没有 permit 被占用，不会永久泄漏。
        """
        with self._backoff_lock:
            state = self._backoff_state.get(provider)
            if state is None:
                return 0.0
            last_429_time, consecutive = state
            elapsed = time.time() - last_429_time
            if elapsed >= self.backoff_window:
                self._backoff_state.pop(provider, None)
                return 0.0
            return max(0.0, self._compute_backoff(consecutive) - elapsed)

    def acquire(self, provider: str) -> threading.BoundedSemaphore:
        """获取 provider 的信号量，必要时 sleep 退避。

        返回信号量对象（调用方必须在 finally 中 release）。
        推荐改用 ``slot()`` 上下文管理器，自动处理释放。

        P1-3(3.1): 退避 sleep 移到 ``sem.acquire()`` **之前**；拿槽成功后
        不再有任何可中断路径，调用方 finally 一定有机会归还 permit。
        旧实现拿槽后 sleep，中断会永久泄漏 permit；持槽 sleep 还把并发压到 ~1。
        """
        remaining = self._backoff_delay(provider)
        if remaining > 0:
            logger.debug("RateLimiter %s: 退避 sleep %.2fs（持槽前）", provider, remaining)
            time.sleep(remaining)
        sem = self._get_semaphore(provider)
        sem.acquire()
        return sem

    def release(self, provider: str, got_429: bool = False) -> None:
        """释放 provider 的信号量。

        若 got_429=True：标记 _backoff_state，触发后续 acquire 的退避。

        .. deprecated::
            ``got_429=True`` 会同时释放信号量+标记退避，若调用方已通过
            ``finally`` 释放过信号量会导致双重释放。新代码应分别调用
            ``release(provider)`` 和 ``mark_429(provider)``。
        """
        sem = self._semaphores.get(provider)
        if sem is not None:
            sem.release()
        if got_429:
            self._mark_backoff(provider)

    def mark_429(self, provider: str) -> None:
        """标记 provider 触发 429 退避（不释放信号量）。

        用于 ``DataFetcherManager.fetch`` 的 429 路径：信号量已在 ``finally``
        中释放，此处只需标记退避状态，避免双重释放。
        """
        self._mark_backoff(provider)

    def _mark_backoff(self, provider: str) -> None:
        """内部：更新 _backoff_state 退避计数。"""
        with self._backoff_lock:
            state = self._backoff_state.get(provider)
            if state is None:
                self._backoff_state[provider] = (time.time(), 1)
            else:
                last_time, consecutive = state
                # 若距上次第 1 次 429 超过窗口，重置计数
                if time.time() - last_time > self.backoff_window:
                    self._backoff_state[provider] = (time.time(), 1)
                else:
                    self._backoff_state[provider] = (time.time(), consecutive + 1)

    @contextmanager
    def slot(self, provider: str) -> Iterator[None]:
        """上下文管理器形式获取 provider 槽位（推荐用法）。

        解决 信号量泄漏：try/finally 强制释放，即便业务代码抛
        KeyboardInterrupt、未捕获的 AssertionError 也能保证信号量归还。

        P1-3(3.1): 退避 sleep 移到持槽之前（与 acquire() 语义一致），
        ``sem.acquire()`` 成功后的 yield 被 try/finally 完整包裹；
        退避期间被中断时尚未持槽，不会泄漏 permit，也不会占槽压低并发。

        用法::

            with limiter.slot("eastmoney"):
                result = fetcher.fetch(code)
                if result is None:
                    raise SomeRetryable()
                # 异常会自动 release
        """
        remaining = self._backoff_delay(provider)
        if remaining > 0:
            logger.debug("RateLimiter.slot %s: 退避 sleep %.2fs（持槽前）", provider, remaining)
            time.sleep(remaining)
        sem = self._get_semaphore(provider)
        sem.acquire()
        try:
            yield
        finally:
            sem.release()

    def is_provider_disabled(self, provider: str) -> bool:
        """检查 provider 当前是否在退避窗口内（用作 circuit breaker 的旁路信号）。

        v1.16.0 Batch 2 fetcher_base 可在切源前调用此方法，
        避免对退避中的 provider 发起新请求，从而让 circuit breaker 与
        RateLimiter 形成正交抑制（一个抑制并发，一个抑制恢复）。
        """
        with self._backoff_lock:
            state = self._backoff_state.get(provider)
            if state is None:
                return False
            last_429_time, _consecutive = state
            return (time.time() - last_429_time) < self.backoff_window

    def reset(self, provider: str = "") -> None:
        """重置 provider（或全部）的限流状态，主要用于测试。"""
        with self._backoff_lock:
            if provider:
                self._backoff_state.pop(provider, None)
            else:
                self._backoff_state.clear()

    def stats(self) -> dict:
        """返回当前限流状态（用于监控/调试）。"""
        with self._backoff_lock:
            return {
                "max_concurrent": self.max_concurrent,
                "providers": list(self._semaphores.keys()),
                "backoff_state": {
                    p: {"consecutive_429": c, "elapsed": time.time() - t} for p, (t, c) in self._backoff_state.items()
                },
            }


# ---------- 全局单例 ----------

_rate_limiter: RateLimiter | None = None
_rate_limiter_lock = threading.Lock()


def _load_rate_limit_config() -> dict:
    """从 data_source.yaml 加载 rate_limit 配置。"""
    try:
        from config.loader import ConfigLoader

        return ConfigLoader.load("data_source.yaml").get("rate_limit", {})
    except Exception as e:
        log_silent_fallback("rate_limiter._load_rate_limit_config", e)
        logger.debug("加载 rate_limit 配置失败，使用默认值: %s", e)
        return {}


def get_rate_limiter() -> RateLimiter:
    """获取全局 RateLimiter 单例（首次按 YAML 配置初始化）。"""
    global _rate_limiter
    if _rate_limiter is not None:
        return _rate_limiter
    with _rate_limiter_lock:
        if _rate_limiter is None:
            cfg = _load_rate_limit_config()
            _rate_limiter = RateLimiter(
                max_concurrent=int(cfg.get("default_max_concurrent", _DEFAULT_MAX_CONCURRENT)),
                backoff_base=float(cfg.get("backoff_base", _DEFAULT_BACKOFF_BASE)),
                backoff_cap=float(cfg.get("backoff_cap", _DEFAULT_BACKOFF_CAP)),
                backoff_window=float(cfg.get("backoff_window", _DEFAULT_BACKOFF_WINDOW)),
            )
        return _rate_limiter


def reset_rate_limiter() -> None:
    """重置全局单例（仅用于测试隔离）。"""
    global _rate_limiter
    with _rate_limiter_lock:
        _rate_limiter = None


@contextmanager
def rate_limiter_slot(provider: str) -> Iterator[None]:
    """使用全局 RateLimiter 单例的 slot 上下文管理器（推荐入口）。

    v1.16.0 Batch 2：解决 信号量泄漏，业务代码可直接::

        from common.rate_limiter import rate_limiter_slot

        with rate_limiter_slot("eastmoney"):
            result = fetcher.fetch(code)
    """
    limiter = get_rate_limiter()
    with limiter.slot(provider):
        yield


def is_provider_disabled(provider: str) -> bool:
    """全局旁路信号：provider 当前是否处于 429 退避窗口（v1.16.0 新增）。

    fetcher_base 可在切源前调用，避免对退避中的 provider 发起请求。
    """
    return get_rate_limiter().is_provider_disabled(provider)
