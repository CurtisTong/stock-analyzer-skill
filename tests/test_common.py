"""
common.py 单元测试：覆盖熔断器、缓存、异常处理、连接池。
"""

import http.client
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from common import (
    BaseFetcher,
    CircuitBreaker,
    CircuitState,
    DataError,
    DataFetcherManager,
    NOT_HANDLED,
    cache_cleanup,
    cache_get,
    cache_set,
    cache_key_for_stock,
    clamp,
    to_float,
    err,
)
from common.http import (
    _get_connection,
    _return_connection,
    _connection_pool,
    _pool_lock,
)
from common.utils import parallel_map


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
        cb = CircuitBreaker(
            "test", failure_threshold=2, recovery_timeout=0, half_open_max=1
        )
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
        assert cb.state in (
            CircuitState.CLOSED,
            CircuitState.OPEN,
            CircuitState.HALF_OPEN,
        )


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


# ====================================================================
# 5. parallel_map 超时返回部分结果
# ====================================================================
class TestParallelMap:
    """parallel_map graceful timeout。"""

    def test_parallel_map_partial_results(self):
        """超时时返回已完成的部分结果，而非抛异常。"""

        def task(item):
            if item in ("slow1", "slow2"):
                time.sleep(10)  # 模拟超时任务
            return f"result_{item}"

        items = ["fast1", "fast2", "fast3", "slow1", "slow2"]
        results = parallel_map(task, items, timeout=1)

        # 3 个快速任务应返回有效结果
        assert results["fast1"] == "result_fast1"
        assert results["fast2"] == "result_fast2"
        assert results["fast3"] == "result_fast3"
        # 超时任务不在结果中（被 cancel）或值为 None
        assert len(results) >= 3


# ====================================================================
# 6. 连接池
# ====================================================================
class TestConnectionPool:
    """http.client 连接池复用。"""

    def setup_method(self):
        """每个测试前清空连接池。"""
        with _pool_lock:
            _connection_pool.clear()

    def teardown_method(self):
        """每个测试后清空连接池。"""
        with _pool_lock:
            for conn in _connection_pool.values():
                try:
                    conn.close()
                except Exception:
                    pass
            _connection_pool.clear()

    def test_get_connection_returns_https(self):
        """HTTPS URL 创建 HTTPSConnection。"""
        conn = _get_connection(
            "https://api.example.com:443", "https", "api.example.com", 443
        )
        assert isinstance(conn, http.client.HTTPSConnection)
        conn.close()

    def test_get_connection_returns_http(self):
        """HTTP URL 创建 HTTPConnection。"""
        conn = _get_connection(
            "http://api.example.com:80", "http", "api.example.com", 80
        )
        assert isinstance(conn, http.client.HTTPConnection)
        conn.close()

    def test_get_connection_with_port(self):
        """带端口的 URL 使用指定端口。"""
        conn = _get_connection(
            "https://api.example.com:8443", "https", "api.example.com", 8443
        )
        assert conn.host == "api.example.com"
        assert conn.port == 8443
        conn.close()

    def test_return_connection_pools(self):
        """归还的连接被放入池中（列表形式）。"""
        key = "https://api.example.com:443"
        conn = _get_connection(key, "https", "api.example.com", 443)
        conn.sock = MagicMock()
        _return_connection(key, conn)
        assert key in _connection_pool
        assert conn in _connection_pool[key]

    def test_get_connection_reuses_pooled(self):
        """池中有可用连接时复用。"""
        key = "https://api.example.com:443"
        conn = _get_connection(key, "https", "api.example.com", 443)
        conn.sock = MagicMock()
        _return_connection(key, conn)
        conn2 = _get_connection(key, "https", "api.example.com", 443)
        assert conn2 is conn

    def test_get_connection_evicts_stale(self):
        """池中连接已断开时创建新连接。"""
        key = "https://api.example.com:443"
        conn = _get_connection(key, "https", "api.example.com", 443)
        conn.sock = MagicMock()
        _return_connection(key, conn)
        conn.sock = None
        conn2 = _get_connection(key, "https", "api.example.com", 443)
        assert conn2 is not conn
        conn2.close()

    def test_pool_thread_safety(self):
        """并发访问连接池无异常。"""
        errors = []
        key = "https://api.example.com:443"

        def worker():
            try:
                for _ in range(50):
                    conn = _get_connection(key, "https", "api.example.com", 443)
                    conn.sock = MagicMock()
                    _return_connection(key, conn)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0


# ====================================================================
# 7. DataFetcherManager 优先级覆盖
# ====================================================================


class _StubFetcher(BaseFetcher):
    """测试用 fetcher，返回固定值。"""

    def __init__(self, name: str, priority: int = 0, result=None):
        super().__init__(name, priority)
        self._result = result if result is not None else {"source": name}

    def fetch(self, code: str, **kwargs):
        return self._result


class TestDataFetcherManager:
    """DataFetcherManager 优先级覆盖与故障切换。"""

    def test_sort_by_default_priority(self):
        """无 source_config 时按 fetcher 默认优先级排序。"""
        f1 = _StubFetcher("low_quote", priority=1)
        f2 = _StubFetcher("high_quote", priority=10)
        mgr = DataFetcherManager([f1, f2])
        assert mgr.fetchers[0].name == "high_quote"
        assert mgr.fetchers[1].name == "low_quote"

    def test_source_config_overrides_priority(self):
        """source_config 覆盖 fetcher 默认优先级。"""
        f1 = _StubFetcher("tencent_quote", priority=1)
        f2 = _StubFetcher("sina_quote", priority=10)
        config = {
            "tencent": {"priority": 10, "enabled": True},
            "sina": {"priority": 1, "enabled": True},
        }
        mgr = DataFetcherManager([f1, f2], source_config=config)
        # tencent 优先级被覆盖为 10，sina 被覆盖为 1
        assert mgr.fetchers[0].name == "tencent_quote"
        assert mgr.fetchers[0].priority == 10
        assert mgr.fetchers[1].name == "sina_quote"
        assert mgr.fetchers[1].priority == 1

    def test_source_config_partial_override(self):
        """source_config 只覆盖匹配的 fetcher，未匹配的保持原优先级。"""
        f1 = _StubFetcher("tencent_quote", priority=5)
        f2 = _StubFetcher("custom_quote", priority=8)
        config = {
            "tencent": {"priority": 10},
        }
        mgr = DataFetcherManager([f1, f2], source_config=config)
        assert mgr.fetchers[0].name == "tencent_quote"
        assert mgr.fetchers[0].priority == 10
        assert mgr.fetchers[1].name == "custom_quote"
        assert mgr.fetchers[1].priority == 8  # 未被覆盖

    def test_source_config_empty(self):
        """空 source_config 不改变优先级。"""
        f1 = _StubFetcher("tencent_quote", priority=5)
        f2 = _StubFetcher("sina_quote", priority=10)
        mgr = DataFetcherManager([f1, f2], source_config={})
        assert mgr.fetchers[0].name == "sina_quote"
        assert mgr.fetchers[1].name == "tencent_quote"

    def test_fetch_uses_priority_order(self):
        """fetch 按优先级从高到低尝试。"""
        calls = []
        f1 = _StubFetcher("high", priority=10, result=None)  # 返回 None 触发失败
        f1.fetch = lambda code, **kw: calls.append("high") or None
        f2 = _StubFetcher("low", priority=1, result={"ok": True})
        f2.fetch = lambda code, **kw: calls.append("low") or {"ok": True}
        mgr = DataFetcherManager([f1, f2])
        result = mgr.fetch("sh600519")
        assert result == {"ok": True}
        assert calls == ["high", "low"]

    def test_fetch_stops_at_first_success(self):
        """fetch 在第一个成功源停止，不尝试后续源。"""
        calls = []
        f1 = _StubFetcher("first", priority=10)
        f1.fetch = lambda code, **kw: calls.append("first") or {"data": 1}
        f2 = _StubFetcher("second", priority=5)
        f2.fetch = lambda code, **kw: calls.append("second") or {"data": 2}
        mgr = DataFetcherManager([f1, f2])
        result = mgr.fetch("sh600519")
        assert result == {"data": 1}
        assert calls == ["first"]

    def test_fetch_skips_unavailable(self):
        """fetch 跳过熔断器阻止的 fetcher。"""
        f1 = _StubFetcher("broken", priority=10)
        f1.circuit_breaker.record_failure()
        f1.circuit_breaker.record_failure()
        f1.circuit_breaker.record_failure()
        f1.circuit_breaker.record_failure()
        f1.circuit_breaker.record_failure()  # 达到阈值，熔断
        f2 = _StubFetcher("working", priority=5, result={"ok": True})
        mgr = DataFetcherManager([f1, f2])
        result = mgr.fetch("sh600519")
        assert result == {"ok": True}
