"""
common.py 单元测试：覆盖熔断器、缓存、异常处理。
"""
import threading
import time
import pytest

from common import (
    CircuitBreaker,
    CircuitState,
    DataError,
    cache_cleanup,
    cache_get,
    cache_set,
    cache_key_for_stock,
    clamp,
    to_float,
    err,
)


# ====================================================================
# 1. CircuitBreaker 线程安全
# ====================================================================
class TestCircuitBreaker:
    """熔断器核心逻辑。"""

    def test_initial_state_closed(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_opens_after_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.01)
        assert cb.can_execute() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_closes_after_success_in_half_open(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0, half_open_max=1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.01)
        cb.can_execute()  # transition to HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_reset(self):
        cb = CircuitBreaker("test", failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_thread_safety(self):
        """并发调用 1000 次无状态异常。"""
        cb = CircuitBreaker("test", failure_threshold=10, recovery_timeout=0)
        errors = []

        def worker():
            try:
                for _ in range(100):
                    if cb.can_execute():
                        if time.time() % 2 > 1:
                            cb.record_success()
                        else:
                            cb.record_failure()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert cb.state in (CircuitState.CLOSED, CircuitState.OPEN, CircuitState.HALF_OPEN)


# ====================================================================
# 2. DataError 异常
# ====================================================================
class TestDataError:
    """err() 改为抛出异常。"""

    def test_err_raises_exception(self):
        with pytest.raises(DataError, match="测试错误"):
            err("测试错误")

    def test_data_error_is_exception(self):
        assert issubclass(DataError, Exception)


# ====================================================================
# 3. 工具函数
# ====================================================================
class TestUtilities:
    """clamp, to_float 等工具函数。"""

    def test_clamp_basic(self):
        assert clamp(50, 0, 100) == 50
        assert clamp(-10, 0, 100) == 0
        assert clamp(150, 0, 100) == 100

    def test_to_float_normal(self):
        assert to_float("12.5") == 12.5
        assert to_float("1,234") == 1234.0

    def test_to_float_empty(self):
        assert to_float(None) == 0.0
        assert to_float("") == 0.0
        assert to_float("-") == 0.0

    def test_to_float_invalid(self):
        assert to_float("abc") == 0.0


# ====================================================================
# 4. 缓存
# ====================================================================
class TestCache:
    """缓存读写和清理。"""

    def _patch_cache_dir(self, tmp_path, monkeypatch):
        """同时 patch common 和 data.cache 的 CACHE_DIR。"""
        monkeypatch.setattr("common.CACHE_DIR", tmp_path)
        monkeypatch.setattr("data.cache.CACHE_DIR", tmp_path)

    def test_cache_set_get(self, tmp_path, monkeypatch):
        self._patch_cache_dir(tmp_path, monkeypatch)
        cache_set("test_key", b"test_value")
        result = cache_get("test_key", ttl_seconds=60)
        assert result == b"test_value"

    def test_cache_expired(self, tmp_path, monkeypatch):
        self._patch_cache_dir(tmp_path, monkeypatch)
        cache_set("test_key", b"test_value")
        # TTL=0 立即过期
        result = cache_get("test_key", ttl_seconds=0)
        assert result is None

    def test_cache_cleanup(self, tmp_path, monkeypatch):
        self._patch_cache_dir(tmp_path, monkeypatch)
        cache_set("old_key", b"old")
        cache_set("new_key", b"new")
        # 清理 max_age=0 的（全部过期）
        cleaned = cache_cleanup(max_age_seconds=0)
        assert cleaned == 2

    def test_cache_key_for_stock(self):
        key1 = cache_key_for_stock("quote", "sh600519")
        key2 = cache_key_for_stock("quote", "sz000858")
        assert key1 != key2
        assert "sh600519" in key1

    def test_cache_key_with_params(self):
        key1 = cache_key_for_stock("kline", "sh600519", scale=240, datalen=30)
        key2 = cache_key_for_stock("kline", "sh600519", scale=5, datalen=48)
        assert key1 != key2
