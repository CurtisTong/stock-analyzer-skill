"""熔断器实现：线程安全的 closed/open/half-open 状态机。

用于 DataFetcherManager 对数据源的故障隔离。
"""

import threading
import time
from enum import Enum


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """线程安全的熔断器：连续失败 N 次后熔断，超时后半开试探。

    半开期恢复策略（可配置）：
    - 默认（half_open_success_threshold=1）：任一试探成功即 CLOSED（v1.14.2 兼容）
    - 严格（half_open_success_threshold=N）：累计 N 次成功才 CLOSED，
      与 half_open_max 对齐——避免本地网络抽风导致的"假恢复"
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max: int = 3,
        half_open_success_threshold: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max
        self.half_open_success_threshold = half_open_success_threshold

        self._lock = threading.Lock()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: float = 0.0
        self.half_open_success = 0
        self._half_open_attempts = 0
        self._half_open_started: float = 0.0

    def can_execute(self) -> bool:
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_success = 0
                    self._half_open_attempts = 1  # 当前请求计入首次试探
                    self._half_open_started = time.time()
                    return True
                return False
            if self.state == CircuitState.HALF_OPEN:
                if self._half_open_attempts < self.half_open_max:
                    self._half_open_attempts += 1
                    return True
                # 试探次数耗尽：若距进入 HALF_OPEN 已超过 recovery_timeout，重置允许重试。
                # recovery_timeout=0 时不重置（避免无限试探，由 record_failure 回到 OPEN 再等超时）
                if (
                    self.recovery_timeout > 0
                    and time.time() - self._half_open_started > self.recovery_timeout
                ):
                    self._half_open_attempts = 1
                    self._half_open_started = time.time()
                    return True
                return False
            return False

    def record_success(self) -> None:
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                # 半开期累计 half_open_success_threshold 次成功才恢复 CLOSED。
                # threshold=1 时单次成功即恢复（默认行为，与 v1.14.2 测试约定兼容）；
                # 显式传 threshold>1 启用严格守卫（如 half_open_success_threshold=3）。
                self.half_open_success += 1
                if self.half_open_success >= self.half_open_success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self._half_open_attempts = 0
                    self.half_open_success = 0
            elif self.state == CircuitState.CLOSED:
                self.failure_count = 0

    def record_failure(self) -> None:
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self._half_open_attempts = 0
                self._half_open_started = 0.0
            elif self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN

    def reset(self) -> None:
        with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.last_failure_time = 0
            self._half_open_attempts = 0
            self._half_open_started = 0.0


_circuit_breakers: dict[str, CircuitBreaker] = {}
_circuit_breakers_lock = threading.Lock()


def get_circuit_breaker(name: str, **kwargs: int) -> CircuitBreaker:
    """获取命名熔断器单例。"""
    with _circuit_breakers_lock:
        if name not in _circuit_breakers:
            _circuit_breakers[name] = CircuitBreaker(name, **kwargs)
        return _circuit_breakers[name]
