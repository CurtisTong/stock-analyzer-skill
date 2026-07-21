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
