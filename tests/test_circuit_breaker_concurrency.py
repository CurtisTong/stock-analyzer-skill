"""
熔断器半开期竞态测试：验证 half_open_max 控制并发试探数量。
"""

import threading
import time
import pytest

from common import CircuitBreaker, CircuitState


class TestHalfOpenConcurrency:
    """半开期并发试探保护。"""

    def test_half_open_limits_concurrent_attempts(self):
        """100 个线程同时在 OPEN→HALF_OPEN 边界，最多 half_open_max 个能通过。"""
        cb = CircuitBreaker(
            "test", failure_threshold=2, recovery_timeout=0, half_open_max=3
        )
        # 触发熔断
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.01)  # 等待 recovery_timeout

        results = []
        barrier = threading.Barrier(100)

        def worker():
            barrier.wait()  # 同时冲
            ok = cb.can_execute()
            results.append(ok)

        threads = [threading.Thread(target=worker) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        passed = sum(results)
        assert passed == 3, f"期望 3 个线程通过（half_open_max=3），实际 {passed} 个"

    def test_single_attempt_mode(self):
        """half_open_max=1 时只允许单次试探。"""
        cb = CircuitBreaker(
            "test", failure_threshold=2, recovery_timeout=0, half_open_max=1
        )
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.01)

        results = []
        barrier = threading.Barrier(50)

        def worker():
            barrier.wait()
            results.append(cb.can_execute())

        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        passed = sum(results)
        assert passed == 1, f"期望 1 个线程通过（half_open_max=1），实际 {passed} 个"

    def test_success_restores_closed(self):
        """半开期达到 half_open_max 次成功后恢复 CLOSED。"""
        cb = CircuitBreaker(
            "test", failure_threshold=2, recovery_timeout=0, half_open_max=1
        )
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.01)

        assert cb.can_execute() is True  # 进入 HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        # 恢复后所有请求都应通过
        assert cb.can_execute() is True

    def test_failure_back_to_open(self):
        """半开期失败后回到 OPEN，且 recovery_timeout 内请求被拒绝。"""
        cb = CircuitBreaker(
            "test", failure_threshold=2, recovery_timeout=0.05, half_open_max=1
        )
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.1)  # 超过 recovery_timeout

        assert cb.can_execute() is True  # 进入 HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        # record_failure 刚设置 last_failure_time，timeout 未到
        assert cb.can_execute() is False

    def test_counter_blocks_after_max(self):
        """半开期试探次数达到 half_open_max 后，后续请求被拒绝。"""
        cb = CircuitBreaker(
            "test", failure_threshold=2, recovery_timeout=0, half_open_max=2
        )
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.01)

        # 前 2 个请求通过
        assert cb.can_execute() is True
        assert cb.can_execute() is True
        # 第 3 个被拒绝（已达上限）
        assert cb.can_execute() is False

    def test_concurrent_success_failure(self):
        """并发场景：half_open_max 个线程能通过试探，全部成功后电路恢复正常。"""
        cb = CircuitBreaker(
            "test", failure_threshold=2, recovery_timeout=0, half_open_max=1
        )
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.01)

        results = []
        barrier = threading.Barrier(50)

        def worker():
            barrier.wait()
            results.append(cb.can_execute())

        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        passed = sum(results)
        assert passed == 1, f"期望 1 个线程通过（half_open_max=1），实际 {passed} 个"

        # 试探线程成功后电路恢复
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_reset_clears_attempts(self):
        """reset() 清除试探计数器。"""
        cb = CircuitBreaker(
            "test", failure_threshold=2, recovery_timeout=0, half_open_max=1
        )
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.01)
        cb.can_execute()  # 消耗试探次数
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb._half_open_attempts == 0
