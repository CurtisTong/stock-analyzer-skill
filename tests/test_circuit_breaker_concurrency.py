"""
熔断器半开期竞态测试：验证 _half_open_token 保证单次试探。
"""
import threading
import time
import pytest

from common import CircuitBreaker, CircuitState


class TestHalfOpenConcurrency:
    """半开期并发试探保护。"""

    def test_only_one_thread_gets_token(self):
        """100 个线程同时在 OPEN→HALF_OPEN 边界，只有 1 个能拿到 token。"""
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0)
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
        assert passed == 1, f"期望 1 个线程通过，实际 {passed} 个"

    def test_success_restores_closed(self):
        """半开期单次成功后恢复 CLOSED。"""
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.01)

        assert cb.can_execute() is True  # 进入 HALF_OPEN，拿到 token
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        # 恢复后所有请求都应通过
        assert cb.can_execute() is True

    def test_failure_back_to_open(self):
        """半开期失败后回到 OPEN，且 recovery_timeout 内请求被拒绝。"""
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.05)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.1)  # 超过 recovery_timeout

        assert cb.can_execute() is True  # 进入 HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        # record_failure 刚设置 last_failure_time，timeout 未到
        assert cb.can_execute() is False

    def test_token_blocks_subsequent_requests(self):
        """半开期已有线程试探时，后续请求被拒绝。"""
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.01)

        # 第一个线程拿到 token
        assert cb.can_execute() is True
        # 第二个线程被拒绝（token 已被消费）
        assert cb.can_execute() is False

    def test_concurrent_success_failure(self):
        """并发场景：只有 1 个线程能通过试探，成功后电路恢复正常。"""
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0)
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
        assert passed == 1, f"期望 1 个线程通过，实际 {passed} 个"

        # 试探线程成功后电路恢复
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_reset_clears_token(self):
        """reset() 清除 token 状态。"""
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.01)
        cb.can_execute()  # 拿走 token
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb._half_open_token is False
