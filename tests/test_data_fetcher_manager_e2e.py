"""
DataFetcherManager 故障转移 E2E 测试。

覆盖场景：
1. primary 失败 → 自动切到 secondary
2. 全部失败 → 缓存降级
3. primary 熔断后不再被选择
4. NOT_HANDLED 跳过不计失败
5. RateLimitError 直接抛出
"""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from common import (
    BaseFetcher,
    CircuitState,
    DataFetcherManager,
    NOT_HANDLED,
    RateLimitError,
)
from common.circuit_breaker import _circuit_breakers


@pytest.fixture(autouse=True)
def clear_circuit_breakers():
    """每个测试前清理全局熔断器缓存，避免测试间状态干扰。"""
    _circuit_breakers.clear()
    yield
    _circuit_breakers.clear()


# ---------- Mock Fetchers ----------


class MockFetcher(BaseFetcher):
    """可配置的 Mock Fetcher。"""

    def __init__(
        self,
        name: str,
        priority: int = 0,
        fail: bool = False,
        not_handled: bool = False,
        rate_limit: bool = False,
        result: dict = None,
        raise_on_fail: bool = False,
    ):
        super().__init__(name, priority)
        self._fail = fail
        self._not_handled = not_handled
        self._rate_limit = rate_limit
        self._result = result or {"source": name, "data": "ok"}
        self._raise_on_fail = raise_on_fail
        self.call_count = 0

    def fetch(self, code: str, **kwargs) -> dict | None:
        self.call_count += 1
        if self._rate_limit:
            raise RateLimitError(f"{self.name} rate limited")
        if self._not_handled:
            return NOT_HANDLED
        if self._fail:
            if self._raise_on_fail:
                raise ConnectionError(f"{self.name} connection failed")
            return None
        return self._result


# ---------- 测试用例 ----------


class TestFallbackChain:
    """故障转移链测试。"""

    def test_primary_fail_fallback_to_secondary(self):
        """primary 失败 → 自动切到 secondary。"""
        primary = MockFetcher("primary", priority=10, fail=True)
        secondary = MockFetcher("secondary", priority=5, fail=False)

        mgr = DataFetcherManager([primary, secondary])
        result = mgr.fetch("sh600989")

        assert result is not None
        assert result["source"] == "secondary"
        assert primary.call_count == 1
        assert secondary.call_count == 1

    def test_primary_success_no_fallback(self):
        """primary 成功 → 不调用 secondary。"""
        primary = MockFetcher("primary", priority=10, fail=False)
        secondary = MockFetcher("secondary", priority=5, fail=False)

        mgr = DataFetcherManager([primary, secondary])
        result = mgr.fetch("sh600989")

        assert result is not None
        assert result["source"] == "primary"
        assert primary.call_count == 1
        assert secondary.call_count == 0

    def test_priority_ordering(self):
        """fetchers 按 priority 降序排列。"""
        low = MockFetcher("low", priority=1)
        high = MockFetcher("high", priority=10)
        mid = MockFetcher("mid", priority=5)

        mgr = DataFetcherManager([low, high, mid])
        names = [f.name for f in mgr.fetchers]

        assert names == ["high", "mid", "low"]

    def test_three_level_fallback(self):
        """三级故障转移：primary → secondary → tertiary。"""
        primary = MockFetcher("primary", priority=10, fail=True)
        secondary = MockFetcher("secondary", priority=5, fail=True)
        tertiary = MockFetcher("tertiary", priority=1, fail=False)

        mgr = DataFetcherManager([primary, secondary, tertiary])
        result = mgr.fetch("sh600989")

        assert result is not None
        assert result["source"] == "tertiary"
        assert primary.call_count == 1
        assert secondary.call_count == 1
        assert tertiary.call_count == 1


class TestAllFailToCacheFallback:
    """全部失败 → 缓存降级测试。"""

    def test_all_fail_returns_none(self):
        """全部失败且无缓存 → 返回 None。"""
        fetcher1 = MockFetcher("f1", priority=10, fail=True)
        fetcher2 = MockFetcher("f2", priority=5, fail=True)

        mgr = DataFetcherManager([fetcher1, fetcher2])
        result = mgr.fetch("sh600989")

        assert result is None

    def test_fetch_with_cache_fallback_uses_cache(self):
        """全部失败 → 从缓存降级。"""
        fetcher = MockFetcher("f1", priority=10, fail=True)
        cached_data = {"source": "cache", "data": "cached"}

        mgr = DataFetcherManager([fetcher])

        with (
            patch("common.cache.get") as mock_cache_get,
            patch("common.cache.cache_key_for_stock") as mock_key,
        ):
            mock_key.return_value = "cache_key"
            mock_cache_get.return_value = json.dumps(cached_data).encode()

            result = mgr.fetch_with_cache_fallback(
                "sh600989", cache_prefix="quote", cache_ttl=3600
            )

        assert result is not None
        assert result["source"] == "cache"

    def test_fetch_with_cache_fallback_returns_fallback(self):
        """全部失败且无缓存 → 返回 fallback 默认值。"""
        fetcher = MockFetcher("f1", priority=10, fail=True)
        default = {"source": "default"}

        mgr = DataFetcherManager([fetcher])

        with (
            patch("common.cache.get") as mock_cache_get,
            patch("common.cache.cache_key_for_stock") as mock_key,
        ):
            mock_key.return_value = "cache_key"
            mock_cache_get.return_value = None

            result = mgr.fetch_with_cache_fallback(
                "sh600989", cache_prefix="quote", fallback=default
            )

        assert result == default

    def test_fetch_with_cache_fallback_skips_cache_when_success(self):
        """有实时数据时不读缓存。"""
        fetcher = MockFetcher("f1", priority=10, fail=False)

        mgr = DataFetcherManager([fetcher])

        with patch("common.cache.get") as mock_cache_get:
            result = mgr.fetch_with_cache_fallback("sh600989", cache_prefix="quote")

        assert result["source"] == "f1"
        mock_cache_get.assert_not_called()


class TestCircuitBreakerSkip:
    """熔断器跳过测试。"""

    def test_circuit_breaker_skips_open_fetcher(self):
        """primary 熔断后不再被选择，直接用 secondary。"""
        primary = MockFetcher("primary", priority=10, fail=False)
        secondary = MockFetcher("secondary", priority=5, fail=False)

        # 手动触发熔断
        primary.circuit_breaker.state = CircuitState.OPEN
        primary.circuit_breaker.last_failure_time = time.time()

        mgr = DataFetcherManager([primary, secondary])
        result = mgr.fetch("sh600989")

        assert result is not None
        assert result["source"] == "secondary"
        assert primary.call_count == 0  # 熔断，未调用
        assert secondary.call_count == 1

    def test_circuit_breaker_recovery(self):
        """熔断超时后进入半开状态，试探成功恢复正常。"""
        fetcher = MockFetcher("f1", priority=10, fail=False)

        # 模拟熔断 + 超时
        fetcher.circuit_breaker.state = CircuitState.OPEN
        fetcher.circuit_breaker.last_failure_time = time.time() - 120
        fetcher.circuit_breaker.recovery_timeout = 60

        mgr = DataFetcherManager([fetcher])
        result = mgr.fetch("sh600989")

        assert result is not None
        assert fetcher.call_count == 1
        assert fetcher.circuit_breaker.state == CircuitState.CLOSED

    def test_all_circuit_breaker_open(self):
        """所有 fetcher 熔断 → 返回 None。"""
        f1 = MockFetcher("f1", priority=10)
        f2 = MockFetcher("f2", priority=5)

        f1.circuit_breaker.state = CircuitState.OPEN
        f1.circuit_breaker.last_failure_time = time.time()
        f2.circuit_breaker.state = CircuitState.OPEN
        f2.circuit_breaker.last_failure_time = time.time()

        mgr = DataFetcherManager([f1, f2])
        result = mgr.fetch("sh600989")

        assert result is None
        assert f1.call_count == 0
        assert f2.call_count == 0


class TestNotHandled:
    """NOT_HANDLED 跳过测试。"""

    def test_not_handled_skips_without_failure(self):
        """返回 NOT_HANDLED 的 fetcher 不计入失败，继续下一个。"""
        f1 = MockFetcher("f1", priority=10, not_handled=True)
        f2 = MockFetcher("f2", priority=5, fail=False)

        mgr = DataFetcherManager([f1, f2])
        result = mgr.fetch("sh600989")

        assert result is not None
        assert result["source"] == "f2"
        assert f1.call_count == 1
        assert f2.call_count == 1
        # f1 的熔断器不应记录失败
        assert f1.circuit_breaker.failure_count == 0

    def test_all_not_handled(self):
        """所有 fetcher 返回 NOT_HANDLED → 返回 None。"""
        f1 = MockFetcher("f1", priority=10, not_handled=True)
        f2 = MockFetcher("f2", priority=5, not_handled=True)

        mgr = DataFetcherManager([f1, f2])
        result = mgr.fetch("sh600989")

        assert result is None
        assert f1.circuit_breaker.failure_count == 0
        assert f2.circuit_breaker.failure_count == 0


class TestRateLimitError:
    """限流错误测试。"""

    def test_rate_limit_error_falls_through(self):
        """RateLimitError 不再直接抛出，而是记录失败并继续尝试下一个 fetcher。"""
        f1 = MockFetcher("f1", priority=10, rate_limit=True)
        f2 = MockFetcher("f2", priority=5, fail=False)

        mgr = DataFetcherManager([f1, f2])

        # 应返回 f2 的结果而非 raise
        result = mgr.fetch("sh600989")
        assert result is not None
        assert result.get("source") == "f2"

        # f1 记录失败
        assert f1.circuit_breaker.failure_count == 1
        # f2 应被调用
        assert f2.call_count == 1

    def test_rate_limit_all_sources_exhausted(self):
        """所有源都限速时返回 None。"""
        f1 = MockFetcher("f1", priority=10, rate_limit=True)
        f2 = MockFetcher("f2", priority=5, rate_limit=True)

        mgr = DataFetcherManager([f1, f2])

        result = mgr.fetch("sh600989")
        assert result is None
        assert f1.circuit_breaker.failure_count == 1
        assert f2.circuit_breaker.failure_count == 1


class TestSourceConfig:
    """source_config 优先级覆盖测试。"""

    def test_source_config_overrides_priority(self):
        """source_config 可覆盖 fetcher 的 priority。"""
        f1 = MockFetcher("tencent_quote", priority=1)
        f2 = MockFetcher("eastmoney_quote", priority=10)

        config = {
            "tencent": {"priority": 20},
            "eastmoney": {"priority": 5},
        }

        mgr = DataFetcherManager([f1, f2], source_config=config)

        # tencent 被提升到最高
        assert mgr.fetchers[0].name == "tencent_quote"
        assert mgr.fetchers[0].priority == 20
        assert mgr.fetchers[1].name == "eastmoney_quote"
        assert mgr.fetchers[1].priority == 5

    def test_fetch_with_config_overridden_priority(self):
        """覆盖优先级后按新顺序调用。"""
        f1 = MockFetcher("tencent_quote", priority=1, fail=False)
        f2 = MockFetcher("eastmoney_quote", priority=10, fail=False)

        config = {"tencent": {"priority": 20}}

        mgr = DataFetcherManager([f1, f2], source_config=config)
        result = mgr.fetch("sh600989")

        assert result["source"] == "tencent_quote"


class TestFetchWithFallback:
    """fetch_with_fallback 测试。"""

    def test_returns_result_on_success(self):
        """成功时返回结果。"""
        f1 = MockFetcher("f1", priority=10, fail=False)
        mgr = DataFetcherManager([f1])

        result = mgr.fetch_with_fallback("sh600989", fallback={"default": True})
        assert result["source"] == "f1"

    def test_returns_fallback_on_failure(self):
        """失败时返回 fallback。"""
        f1 = MockFetcher("f1", priority=10, fail=True)
        mgr = DataFetcherManager([f1])

        result = mgr.fetch_with_fallback("sh600989", fallback={"default": True})
        assert result == {"default": True}


class TestEdgeCases:
    """边界情况测试。"""

    def test_empty_fetchers(self):
        """空 fetcher 列表 → 返回 None。"""
        mgr = DataFetcherManager([])
        result = mgr.fetch("sh600989")
        assert result is None

    def test_single_fetcher_success(self):
        """单个 fetcher 成功。"""
        f1 = MockFetcher("f1", priority=10, fail=False)
        mgr = DataFetcherManager([f1])

        result = mgr.fetch("sh600989")
        assert result is not None

    def test_single_fetcher_failure(self):
        """单个 fetcher 失败。"""
        f1 = MockFetcher("f1", priority=10, fail=True)
        mgr = DataFetcherManager([f1])

        result = mgr.fetch("sh600989")
        assert result is None

    def test_fetch_records_success_on_circuit_breaker(self):
        """成功后熔断器重置失败计数。"""
        f1 = MockFetcher("f1", priority=10, fail=False)
        f1.circuit_breaker.failure_count = 3

        mgr = DataFetcherManager([f1])
        mgr.fetch("sh600989")

        assert f1.circuit_breaker.failure_count == 0

    def test_fetch_records_failure_on_circuit_breaker(self):
        """异常后熔断器增加失败计数。"""
        f1 = MockFetcher("f1", priority=10, fail=True, raise_on_fail=True)

        mgr = DataFetcherManager([f1])
        mgr.fetch("sh600989")

        assert f1.circuit_breaker.failure_count == 1

    def test_none_return_does_not_trigger_circuit_breaker(self):
        """返回 None（数据不存在）不触发熔断器失败计数。"""
        f1 = MockFetcher("f1", priority=10, fail=True)  # 返回 None，不抛异常

        mgr = DataFetcherManager([f1])
        mgr.fetch("sh600989")

        assert f1.circuit_breaker.failure_count == 0
