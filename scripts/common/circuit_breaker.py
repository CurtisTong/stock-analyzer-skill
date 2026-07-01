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
        self._half_open_attempts = 0

    def can_execute(self) -> bool:
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_success = 0
                    self._half_open_attempts = 1  # 当前请求计入首次试探
                    return True
                return False
            if self.state == CircuitState.HALF_OPEN:
                if self._half_open_attempts < self.half_open_max:
                    self._half_open_attempts += 1
                    return True
                return False
            return False

    def record_success(self) -> None:
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                # 半开期试探成功即恢复 CLOSED（v1.14.2 标准熔断器行为，DataFetcherManager 测试
                # test_circuit_breaker_recovery 依赖此约定）。
                # half_open_success 字段保留为扩展接口，未来如需"N 次成功守卫"可在此启用。
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
            elif self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN

    def reset(self) -> None:
        with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.last_failure_time = 0
            self._half_open_attempts = 0


_circuit_breakers: dict[str, CircuitBreaker] = {}
_circuit_breakers_lock = threading.Lock()


def get_circuit_breaker(name: str, **kwargs: int) -> CircuitBreaker:
    """获取命名熔断器单例。"""
    with _circuit_breakers_lock:
        if name not in _circuit_breakers:
            _circuit_breakers[name] = CircuitBreaker(name, **kwargs)
        return _circuit_breakers[name]
