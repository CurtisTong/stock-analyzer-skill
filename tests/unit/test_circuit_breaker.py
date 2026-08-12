"""CircuitBreaker 单元测试（v2.7 #2 窗口期逻辑固化）。

验证：
- closed/open/half_open 状态机全路径
- half_open_success_threshold 严格恢复守卫
- 半开窗口期节流：每 recovery_timeout 窗口配额 = half_open_max，
  配额耗尽拒绝放行，窗口过期自动续期（确定性，用时间戳快进代替 sleep）
- 并发 can_execute：lock 保护下窗口内并发放行数严格 == half_open_max，
  无历史"attempts 重置分支"导致的不可预测放量
"""

import threading
import time

from common.circuit_breaker import CircuitBreaker, CircuitState


def _enter_half_open(cb: CircuitBreaker) -> bool:
    """把熔断器从 CLOSED 打到 HALF_OPEN 并返回放行结果。"""
    assert cb.can_execute() is True
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    cb.last_failure_time -= cb.recovery_timeout + 1
    return cb.can_execute()


class TestStateMachine:
    """状态机转换。"""

    def test_initial_closed(self):
        cb = CircuitBreaker("t")
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_failure_threshold_trips_open(self):
        cb = CircuitBreaker("t", failure_threshold=3, recovery_timeout=60)
        for _ in range(3):
            assert cb.can_execute() is True
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_open_blocks_until_timeout(self):
        cb = CircuitBreaker("t", failure_threshold=1, recovery_timeout=5)
        assert cb.can_execute() is True
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False
        cb.last_failure_time -= 6
        assert cb.can_execute() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_recovers_to_closed(self):
        cb = CircuitBreaker("t", failure_threshold=1, recovery_timeout=60)
        assert _enter_half_open(cb) is True
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker("t", failure_threshold=1, recovery_timeout=60)
        assert _enter_half_open(cb) is True
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_in_closed_resets_failure_count(self):
        cb = CircuitBreaker("t", failure_threshold=5, recovery_timeout=60)
        for _ in range(2):
            cb.can_execute()
            cb.record_failure()
        assert cb.failure_count == 2
        cb.record_success()
        assert cb.failure_count == 0

    def test_strict_success_threshold_requires_n(self):
        cb = CircuitBreaker(
            "t",
            failure_threshold=1,
            recovery_timeout=60,
            half_open_max=3,
            half_open_success_threshold=3,
        )
        assert _enter_half_open(cb) is True
        # 1~2 次成功仍保持 half_open
        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_reset_restores_closed(self):
        cb = CircuitBreaker("t", failure_threshold=1, recovery_timeout=60)
        assert _enter_half_open(cb) is True
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0


class TestHalfOpenWindow:
    """半开窗口期节流：配额 = half_open_max，窗口过期自动续期。"""

    def test_quota_blocks_after_half_open_max(self):
        cb = CircuitBreaker(
            "t", failure_threshold=1, recovery_timeout=60, half_open_max=2
        )
        assert _enter_half_open(cb) is True
        assert cb.can_execute() is True
        assert cb.can_execute() is False  # 窗口内配额 2 已耗尽
        assert cb.can_execute() is False

    def test_window_expiry_renews_quota(self):
        cb = CircuitBreaker(
            "t", failure_threshold=1, recovery_timeout=60, half_open_max=2
        )
        assert _enter_half_open(cb) is True
        assert cb.can_execute() is True
        assert cb.can_execute() is False
        # 快进窗口：过期后自动续期放行
        cb._half_open_started -= 61
        assert cb.can_execute() is True
        assert cb.can_execute() is True
        assert cb.can_execute() is False

    def test_short_timeout_window_renews_on_real_elapse(self):
        cb = CircuitBreaker(
            "t", failure_threshold=1, recovery_timeout=0.01, half_open_max=1
        )
        assert _enter_half_open(cb) is True
        assert cb.can_execute() is False  # 配额 1 已耗尽
        time.sleep(0.02)
        assert cb.can_execute() is True  # 真实时间流逝后窗口续期

    def test_zero_timeout_never_renews_within_half_open(self):
        """recovery_timeout=0 时半开期不自动续期（防止无限试探）。"""
        cb = CircuitBreaker(
            "t", failure_threshold=1, recovery_timeout=0, half_open_max=1
        )
        assert cb.can_execute() is True
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.last_failure_time -= 100
        assert cb.can_execute() is True  # 进入 half_open（recovery_timeout 被钳制为 1）
        assert cb.can_execute() is False
        time.sleep(0.02)
        assert cb.can_execute() is False  # 窗口不续期


class TestConcurrentWindow:
    """并发下窗口内放行数严格等于 half_open_max（lock 保护）。"""

    def test_concurrent_can_execute_respects_quota(self):
        cb = CircuitBreaker(
            "t", failure_threshold=1, recovery_timeout=60, half_open_max=3
        )
        assert _enter_half_open(cb) is True
        passed: list = []
        lock = threading.Lock()

        def worker():
            if cb.can_execute():
                with lock:
                    passed.append(1)

        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 窗口未过期：严格 == half_open_max（进入半开已消耗 1 配额，余 2），无放量
        assert len(passed) == 2
        assert cb._half_open_attempts == 3

    def test_concurrent_after_window_expiry_next_quota(self):
        cb = CircuitBreaker(
            "t", failure_threshold=1, recovery_timeout=60, half_open_max=2
        )
        assert _enter_half_open(cb) is True
        passed: list = []

        def drain(n: int):
            got = [cb.can_execute() for _ in range(n)]
            passed.extend(g for g in got if g)

        threads = [threading.Thread(target=drain, args=(20,)) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 进入半开已消耗 1 配额，half_open_max=2 余 1
        assert len(passed) == 1
        assert cb.can_execute() is False

        # 快进窗口：下一窗口配额重置
        cb._half_open_started -= 61
        assert cb.can_execute() is True
        assert cb.can_execute() is True
        assert cb.can_execute() is False
