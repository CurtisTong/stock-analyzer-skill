"""WP5 RateLimiter 单元测试。

验证：
- 基础并发控制（Semaphore）
- 429 后退避 sleep
- 连续 429 后指数退避增长
- 退避窗口过期后重置
- 重置 / 统计接口
"""

import time

import pytest

from common.rate_limiter import RateLimiter


class TestRateLimiterBasics:
    """基础并发控制。"""

    def test_default_concurrency(self):
        """默认 max_concurrent=8。"""
        rl = RateLimiter()
        assert rl.max_concurrent == 8
        assert rl.backoff_base == 1.0
        assert rl.backoff_cap == 8.0

    def test_acquire_release_basic(self):
        """acquire / release 基本流程。"""
        rl = RateLimiter(max_concurrent=2)
        rl.acquire("eastmoney")
        rl.acquire("eastmoney")
        # 释放一个后再 acquire 应立即成功
        rl.release("eastmoney")
        rl.acquire("eastmoney")
        rl.release("eastmoney")
        rl.release("eastmoney")

    def test_per_provider_isolation(self):
        """每个 provider 独立的信号量。"""
        rl = RateLimiter(max_concurrent=1)
        sem_em = rl.acquire("eastmoney")
        sem_ak = rl.acquire("akshare")
        # 互不相同的信号量实例
        assert sem_em is not sem_ak
        # 两者各自只占 1 个 slot，互不影响
        assert sem_em._value == 0  # eastmoney 已满
        assert sem_ak._value == 0  # akshare 已满
        rl.release("eastmoney")
        rl.release("akshare")


class TestBackoff:
    """429 退避逻辑。"""

    def test_release_with_429_marks_backoff(self):
        """release(got_429=True) 后，下一个 acquire 应 sleep。"""
        rl = RateLimiter(max_concurrent=1, backoff_base=0.1, backoff_cap=0.1)
        rl.acquire("eastmoney")
        rl.release("eastmoney", got_429=True)
        # 下次 acquire 应 sleep ~0.1s
        start = time.time()
        rl.acquire("eastmoney")
        elapsed = time.time() - start
        assert 0.08 < elapsed < 0.3  # 容忍时间误差
        rl.release("eastmoney")

    def test_no_backoff_after_normal_release(self):
        """正常 release（无 429）→ 下次 acquire 不 sleep。"""
        rl = RateLimiter(max_concurrent=1, backoff_base=2.0)
        rl.acquire("eastmoney")
        rl.release("eastmoney")  # 无 got_429
        start = time.time()
        rl.acquire("eastmoney")
        elapsed = time.time() - start
        assert elapsed < 0.05  # 几乎瞬时
        rl.release("eastmoney")

    def test_consecutive_429_exponential_backoff(self):
        """连续 429 → 指数退避（1s → 2s → 4s）。"""
        rl = RateLimiter(
            max_concurrent=1,
            backoff_base=0.05,
            backoff_cap=0.05,  # 强制 cap=base 简化测试
            backoff_window=10.0,
        )
        # 标记 3 次连续 429
        rl._backoff_state["eastmoney"] = (time.time(), 3)
        # cap=base=0.05，所以 backoff=min(0.05*2^2, 0.05)=0.05
        # 距上次 429 已经 0s，所以应 sleep ~0.05s
        start = time.time()
        rl.acquire("eastmoney")
        elapsed = time.time() - start
        assert 0.04 < elapsed < 0.2
        rl.release("eastmoney")

    def test_backoff_window_reset(self):
        """超过退避窗口后状态自动重置。"""
        rl = RateLimiter(
            max_concurrent=1,
            backoff_base=0.5,
            backoff_cap=2.0,
            backoff_window=0.1,  # 窗口仅 0.1s
        )
        # 标记过去时间
        rl._backoff_state["eastmoney"] = (time.time() - 1.0, 5)
        # 下次 acquire：elapsed > window → 重置，不 sleep
        start = time.time()
        rl.acquire("eastmoney")
        elapsed = time.time() - start
        assert elapsed < 0.05
        # state 已重置
        assert "eastmoney" not in rl._backoff_state
        rl.release("eastmoney")


class TestResetAndStats:
    """重置 + 统计接口。"""

    def test_reset_provider(self):
        """reset(provider) 清除单个 provider 状态。"""
        rl = RateLimiter()
        rl._backoff_state["eastmoney"] = (time.time(), 1)
        rl._backoff_state["akshare"] = (time.time(), 1)
        rl.reset("eastmoney")
        assert "eastmoney" not in rl._backoff_state
        assert "akshare" in rl._backoff_state

    def test_reset_all(self):
        """reset() 不传参 → 清空所有。"""
        rl = RateLimiter()
        rl._backoff_state["eastmoney"] = (time.time(), 1)
        rl._backoff_state["akshare"] = (time.time(), 1)
        rl.reset()
        assert rl._backoff_state == {}

    def test_stats_format(self):
        """stats() 返回结构化字段。"""
        rl = RateLimiter()
        rl._backoff_state["eastmoney"] = (time.time(), 2)
        s = rl.stats()
        assert s["max_concurrent"] == 8
        assert "eastmoney" in s["backoff_state"]
        assert s["backoff_state"]["eastmoney"]["consecutive_429"] == 2


# === v1.16.0 Batch 2 新增测试：contextmanager / circuit breaker 编排 / 鲁棒性 ===
class TestRateLimiterSlotContextManager:
    """验证 slot() 上下文管理器的 try/finally 信号量释放行为（P1-1.1 修复）。"""

    def test_slot_releases_on_normal_exit(self):
        """正常路径：with 块退出后信号量被释放，下一次 acquire() 可立即获得。"""
        rl = RateLimiter(max_concurrent=1)
        with rl.slot("eastmoney"):
            sem = rl._semaphores["eastmoney"]
            assert sem._value == 0  # 占满
        # 退出后再 acquire 应能成功
        sem2 = rl._get_semaphore("eastmoney")
        assert sem2._value == 1  # 已释放

    def test_slot_releases_on_exception(self):
        """异常路径：业务代码抛异常后信号量仍被释放（P1-1.1 信号量泄漏修复）。"""
        rl = RateLimiter(max_concurrent=1)
        with pytest.raises(RuntimeError):
            with rl.slot("eastmoney"):
                raise RuntimeError("业务异常")
        # 信号量已归还
        sem = rl._get_semaphore("eastmoney")
        assert sem._value == 1  # 已释放

    def test_slot_releases_on_keyboard_interrupt(self):
        """KeyboardInterrupt 路径：模拟 KeyboardInterrupt 后信号量仍被释放。"""
        rl = RateLimiter(max_concurrent=1)
        try:
            with rl.slot("eastmoney"):
                raise KeyboardInterrupt("Ctrl+C")
        except KeyboardInterrupt:
            pass
        # 信号量已归还——保证后续请求不被卡死
        sem = rl._get_semaphore("eastmoney")
        assert sem._value == 1


class TestRateLimiterProviderDisabled:
    """验证 is_provider_disabled() 用作 circuit breaker 旁路信号（P1-1.2 修复）。"""

    def test_disabled_returns_false_when_no_history(self):
        rl = RateLimiter()
        assert rl.is_provider_disabled("eastmoney") is False

    def test_disabled_returns_true_within_window(self):
        rl = RateLimiter(backoff_window=30.0)
        rl._backoff_state["eastmoney"] = (time.time(), 1)
        assert rl.is_provider_disabled("eastmoney") is True

    def test_disabled_returns_false_after_window_expires(self):
        rl = RateLimiter(backoff_window=0.1)
        rl._backoff_state["eastmoney"] = (time.time() - 1.0, 1)  # 1 秒前
        assert rl.is_provider_disabled("eastmoney") is False


class TestRateLimiterDCLIdempotency:
    """验证 get_rate_limiter() 双检锁的幂等性。"""

    def test_get_rate_limiter_returns_same_singleton(self):
        """多次调用返回同一对象。"""
        from common.rate_limiter import get_rate_limiter, reset_rate_limiter

        reset_rate_limiter()
        try:
            a = get_rate_limiter()
            b = get_rate_limiter()
            c = get_rate_limiter()
            assert a is b is c
        finally:
            reset_rate_limiter()

    def test_get_rate_limiter_thread_safe(self):
        """10 个线程并发调 get_rate_limiter()，应共享同一实例。"""
        from common.rate_limiter import get_rate_limiter, reset_rate_limiter
        import threading

        reset_rate_limiter()
        results = []
        lock = threading.Lock()

        def worker():
            rl = get_rate_limiter()
            with lock:
                results.append(id(rl))

        try:
            threads = [threading.Thread(target=worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            assert len(set(results)) == 1  # 10 个线程共享同一实例
        finally:
            reset_rate_limiter()


class TestRateLimiterBackoffCumulative:
    """验证连续 4 次 429 后退避状态正确累积但不超过 cap。"""

    def test_4_consecutive_429s_backoff_capped(self):
        rl = RateLimiter(backoff_base=1.0, backoff_cap=4.0, backoff_window=60.0)
        # 模拟 4 次 429 累积
        for i in range(1, 5):
            rl.release("eastmoney", got_429=True)
        # consecutive 应为 4
        _, consecutive = rl._backoff_state["eastmoney"]
        assert consecutive == 4
        # 计算退避：1*2^3=8 → cap=4
        backoff = rl._compute_backoff(consecutive)
        assert backoff == 4.0  # cap 生效

    def test_consecutive_429_resets_after_window(self):
        rl = RateLimiter(backoff_window=0.1)
        rl.release("eastmoney", got_429=True)
        rl.release("eastmoney", got_429=True)
        _, consecutive = rl._backoff_state["eastmoney"]
        assert consecutive == 2
        # 等待窗口过期
        time.sleep(0.15)
        rl.release("eastmoney", got_429=True)
        _, consecutive = rl._backoff_state["eastmoney"]
        assert consecutive == 1  # 重置
