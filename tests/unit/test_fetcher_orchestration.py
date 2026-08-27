"""DataFetcherManager 编排逻辑 + fetch_with_breaker / fetch_with_fallback 单元测试。

背景：lhb/event fetcher 与 DataFetcherManager 编排逻辑此前全域零测试覆盖，
是 （日期字段 null 崩溃）等 P0 问题能长期存在的根因。本文件覆盖编排关键分支：

1. 多源降级（源 A 抛异常 -> 源 B 返回数据）
2. 熔断 open 跳过（fetcher.is_available()=False 时不调用 fetch）
3. is_provider_disabled 跳过（provider 在 429 退避窗口内时跳过）
4. NOT_HANDLED 跳过（fetcher 返回 NOT_HANDLED 时换下一个源）
5. None 不熔断（fetcher 返回 None 时不调 on_failure，继续下一源）
6. 异常触发熔断（fetcher 抛异常时调 on_failure）
7. fetch_with_breaker 基本路径（成功返回 / 异常返回 None / RateLimitError 返回 None）
8. fetch_with_fallback 多源降级（按 priority 降序遍历）

设计：
- 用 FakeFetcher（可控 priority / 抛异常 / 返回 None / 返回 NOT_HANDLED），
  不依赖真实网络。
- 每个测试通过 autouse fixture 重置 RateLimiter 单例 + CircuitBreaker 字典，
  保证隔离。
"""

from __future__ import annotations

import pytest

from common.fetcher_base import (
    BaseFetcher,
    DataFetcherManager,
    NOT_HANDLED,
    fetch_with_breaker,
    fetch_with_fallback,
)
from common.exceptions import HTTPStatusError, RateLimitError

# ═══════════════════════════════════════════════════════════════
# 测试隔离 fixture：重置 RateLimiter 单例 + CircuitBreaker 全局字典
# ═══════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _reset_global_singletons():
    """每个测试前重置 RateLimiter 单例与 CircuitBreaker 全局字典。

    conftest.py 的 _reload_config_loader 只重载 YAML 缓存；
    RateLimiter / CircuitBreaker 是进程级单例，需在此显式清理，
    避免上一个测试的退避状态 / 熔断状态泄漏到下一个测试。
    """
    from common import circuit_breaker as cb_mod
    from common.rate_limiter import reset_rate_limiter

    reset_rate_limiter()
    with cb_mod._circuit_breakers_lock:
        cb_mod._circuit_breakers.clear()
    yield
    # teardown：同样清理，避免本测试的状态影响后续测试
    reset_rate_limiter()
    with cb_mod._circuit_breakers_lock:
        cb_mod._circuit_breakers.clear()


# ═══════════════════════════════════════════════════════════════
# FakeFetcher：可控行为的数据源替身
# ═══════════════════════════════════════════════════════════════


class FakeFetcher(BaseFetcher):
    """可控行为的 fetcher。

    behavior 可取：
    - "data"：返回 payload（默认 {"src": name}）
    - "none"：返回 None
    - "not_handled"：返回 NOT_HANDLED
    - raise：抛 raise_exc
    """

    def __init__(
        self,
        name: str,
        priority: int = 0,
        behavior: str = "data",
        payload: object = None,
        raise_exc: Exception | None = None,
    ):
        # provider 由 name 推断（含已知 provider 后缀时取后缀，否则取首段）
        super().__init__(name, priority=priority)
        self.behavior = behavior
        self.payload = payload if payload is not None else {"src": name}
        self.raise_exc = raise_exc
        self.call_count = 0
        self.success_count = 0
        self.failure_count = 0

    def fetch(self, code: str = "", **kwargs):
        self.call_count += 1
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.behavior == "none":
            return None
        if self.behavior == "not_handled":
            return NOT_HANDLED
        return self.payload

    def on_success(self):
        self.success_count += 1
        super().on_success()

    def on_failure(self):
        self.failure_count += 1
        super().on_failure()


# ═══════════════════════════════════════════════════════════════
# DataFetcherManager.fetch 编排分支
# ═══════════════════════════════════════════════════════════════


class TestDataFetcherManagerFallback:
    """DataFetcherManager.fetch 的多源降级与跳过逻辑。"""

    def test_fallback_on_exception(self):
        """源 A 抛异常 -> 触发 on_failure -> 降级到源 B 返回数据。"""
        a = FakeFetcher("a_eastmoney", priority=10, raise_exc=RuntimeError("boom"))
        b = FakeFetcher("b_tencent", priority=5, behavior="data")
        mgr = DataFetcherManager([a, b])

        result = mgr.fetch("600519")

        assert result == {"src": "b_tencent"}
        assert a.call_count == 1
        assert a.failure_count == 1  # 异常触发 on_failure
        assert b.call_count == 1
        assert b.success_count == 1

    def test_fallback_on_not_handled(self):
        """源 A 返回 NOT_HANDLED -> 换下一个源（不触发 on_success/on_failure）。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="not_handled")
        b = FakeFetcher("b_tencent", priority=5, behavior="data")
        mgr = DataFetcherManager([a, b])

        result = mgr.fetch("600519")

        assert result == {"src": "b_tencent"}
        assert a.call_count == 1
        assert a.success_count == 0  # NOT_HANDLED 不计成功
        assert a.failure_count == 0  # NOT_HANDLED 不计失败
        assert b.success_count == 1

    def test_none_does_not_trigger_breaker(self):
        """源 A 返回 None（数据不存在）-> 不调 on_failure，继续下一源。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="none")
        b = FakeFetcher("b_tencent", priority=5, behavior="data")
        mgr = DataFetcherManager([a, b])

        result = mgr.fetch("600519")

        assert result == {"src": "b_tencent"}
        assert a.failure_count == 0  # None 不触发熔断
        assert a.success_count == 0  # None 也不计成功
        assert b.success_count == 1

    def test_all_none_returns_none(self):
        """所有源均返回 None -> 返回 None（数据不存在，非失败）。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="none")
        b = FakeFetcher("b_tencent", priority=5, behavior="none")
        mgr = DataFetcherManager([a, b])

        result = mgr.fetch("600519")

        assert result is None
        assert a.failure_count == 0
        assert b.failure_count == 0

    def test_exception_triggers_on_failure(self):
        """fetcher 抛异常时调 on_failure，且 last_error 被记录。"""
        err = RuntimeError("network down")
        a = FakeFetcher("a_eastmoney", priority=10, raise_exc=err)
        mgr = DataFetcherManager([a])

        result = mgr.fetch("600519")

        assert result is None
        assert a.failure_count == 1
        assert mgr.last_error is err

    def test_http_status_error_does_not_trigger_breaker(self):
        """HTTPStatusError（4xx 业务错误）不计入熔断，直接换源。

        P2-H2：404 等业务错误不应误熔断数据源。
        """
        err = HTTPStatusError("http://x", 404, "not found")
        a = FakeFetcher("a_eastmoney", priority=10, raise_exc=err)
        b = FakeFetcher("b_tencent", priority=5, behavior="data")
        mgr = DataFetcherManager([a, b])

        result = mgr.fetch("600519")

        assert result == {"src": "b_tencent"}
        assert a.failure_count == 0  # 4xx 不熔断
        assert mgr.last_error is err

    def test_priority_ordering_desc(self):
        """按 priority 降序遍历，高优先级先命中即返回。"""
        high = FakeFetcher("high_eastmoney", priority=100, behavior="data")
        low = FakeFetcher("low_tencent", priority=1, behavior="data")
        # 传入顺序与优先级相反，验证内部会排序
        mgr = DataFetcherManager([low, high])

        result = mgr.fetch("600519")

        assert result == {"src": "high_eastmoney"}
        assert high.call_count == 1
        assert low.call_count == 0  # 高优先级命中后未调用低优先级

    def test_skips_unavailable_fetcher(self):
        """熔断器 open（is_available()=False）时跳过该 fetcher，不调用 fetch。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="data")
        # 手动把 a 的熔断器打到 OPEN
        a.circuit_breaker.state = a.circuit_breaker.state.OPEN
        a.circuit_breaker.failure_count = 99
        a.circuit_breaker.last_failure_time = __import__("time").time()
        b = FakeFetcher("b_tencent", priority=5, behavior="data")
        mgr = DataFetcherManager([a, b])

        result = mgr.fetch("600519")

        assert result == {"src": "b_tencent"}
        assert a.call_count == 0  # 熔断中，未调用
        assert b.call_count == 1

    def test_skips_provider_in_backoff_window(self):
        """provider 在 429 退避窗口内（is_provider_disabled=True）时跳过。"""
        from common.rate_limiter import get_rate_limiter

        a = FakeFetcher("a_eastmoney", priority=10, behavior="data")
        b = FakeFetcher("b_tencent", priority=5, behavior="data")
        mgr = DataFetcherManager([a, b])

        # 标记 eastmoney 进入退避窗口
        limiter = get_rate_limiter()
        import time

        limiter._backoff_state["eastmoney"] = (time.time(), 1)

        result = mgr.fetch("600519")

        assert result == {"src": "b_tencent"}
        assert a.call_count == 0  # 退避窗口内，跳过
        assert b.call_count == 1

    def test_invalid_code_returns_none(self):
        """非法 code（含特殊字符）直接返回 None，不调用任何 fetcher。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="data")
        mgr = DataFetcherManager([a])

        result = mgr.fetch("bad code!")

        assert result is None
        assert a.call_count == 0

    def test_empty_code_returns_none(self):
        """空 code 返回 None。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="data")
        mgr = DataFetcherManager([a])

        assert mgr.fetch("") is None
        assert a.call_count == 0

    def test_429_triggers_retry_then_fallback(self):
        """429 触发退避后重试主源一次，仍失败则换源。

        遇 429 时退避后重试主源一次，避免被切到数据更少的次源；
        重试仍 429 才切到下一个源。
        """
        a = FakeFetcher("a_eastmoney", priority=10, raise_exc=RateLimitError("u"))
        b = FakeFetcher("b_tencent", priority=5, behavior="data")
        mgr = DataFetcherManager([a, b])

        result = mgr.fetch("600519")

        assert result == {"src": "b_tencent"}
        # 主源被调用 2 次（首次 + 429 重试一次），随后切到次源
        assert a.call_count == 2
        assert b.call_count == 1
        assert isinstance(mgr.last_error, RateLimitError)


class TestDataFetcherManagerHelpers:
    """DataFetcherManager 的 fetch_with_fallback / fetch_with_cache_fallback 辅助方法。"""

    def test_fetch_with_fallback_returns_data(self):
        """fetch 成功时返回数据。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="data")
        mgr = DataFetcherManager([a])

        assert mgr.fetch_with_fallback("600519") == {"src": "a_eastmoney"}

    def test_fetch_with_fallback_returns_default(self):
        """所有源无数据时返回传入的 fallback。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="none")
        mgr = DataFetcherManager([a])

        assert mgr.fetch_with_fallback("600519", fallback="DEFAULT") == "DEFAULT"


# ═══════════════════════════════════════════════════════════════
# fetch_with_breaker 基本路径
# ═══════════════════════════════════════════════════════════════


class TestFetchWithBreaker:
    """fetch_with_breaker 的成功 / 异常 / 限速分支。"""

    def test_success_returns_result(self):
        """fetch 成功 -> 返回结果并记录 on_success。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="data")

        result = fetch_with_breaker(a, "600519")

        assert result == {"src": "a_eastmoney"}
        assert a.success_count == 1
        assert a.failure_count == 0

    def test_exception_returns_none_and_triggers_failure(self):
        """fetch 抛异常 -> 返回 None 并调 on_failure。"""
        a = FakeFetcher("a_eastmoney", priority=10, raise_exc=RuntimeError("boom"))

        result = fetch_with_breaker(a, "600519")

        assert result is None
        assert a.failure_count == 1
        assert a.success_count == 0

    def test_rate_limit_error_returns_none_no_failure(self):
        """RateLimitError(429) -> 返回 None，但不计入熔断失败。"""
        a = FakeFetcher("a_eastmoney", priority=10, raise_exc=RateLimitError("u"))

        result = fetch_with_breaker(a, "600519")

        assert result is None
        assert a.failure_count == 0  # 429 不熔断
        assert a.success_count == 0

    def test_none_result_no_success_no_failure(self):
        """fetch 返回 None -> 原样返回 None，不记成功/失败（数据不存在）。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="none")

        result = fetch_with_breaker(a, "600519")

        assert result is None
        assert a.success_count == 0
        assert a.failure_count == 0

    def test_not_handled_returned_as_is(self):
        """fetch 返回 NOT_HANDLED -> 原样返回（不记成功/失败）。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="not_handled")

        result = fetch_with_breaker(a, "600519")

        assert result is NOT_HANDLED
        assert a.success_count == 0
        assert a.failure_count == 0

    def test_unavailable_fetcher_returns_none(self):
        """熔断器 open 时返回 None，不调用 fetch。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="data")
        a.circuit_breaker.state = a.circuit_breaker.state.OPEN
        import time

        a.circuit_breaker.last_failure_time = time.time()
        a.circuit_breaker.failure_count = 99

        result = fetch_with_breaker(a, "600519")

        assert result is None
        assert a.call_count == 0

    def test_invalid_code_returns_none(self):
        """非法 code 直接返回 None。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="data")

        assert fetch_with_breaker(a, "bad;code") is None
        assert a.call_count == 0

    def test_provider_in_backoff_window_returns_none(self):
        """provider 在 429 退避窗口内时返回 None，不调用 fetch。"""
        from common.rate_limiter import get_rate_limiter
        import time

        a = FakeFetcher("a_eastmoney", priority=10, behavior="data")
        limiter = get_rate_limiter()
        limiter._backoff_state["eastmoney"] = (time.time(), 1)

        result = fetch_with_breaker(a, "600519")

        assert result is None
        assert a.call_count == 0  # 退避窗口内跳过


# ═══════════════════════════════════════════════════════════════
# fetch_with_fallback 多源降级
# ═══════════════════════════════════════════════════════════════


class TestFetchWithFallback:
    """fetch_with_fallback 按 priority 降序遍历多源。"""

    def test_single_fetcher_delegates_to_breaker(self):
        """仅 1 个 fetcher 时等价于 fetch_with_breaker。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="data")

        result = fetch_with_fallback([a], "600519")

        assert result == {"src": "a_eastmoney"}
        assert a.success_count == 1

    def test_empty_fetchers_returns_none(self):
        """空 fetcher 列表返回 None。"""
        assert fetch_with_fallback([], "600519") is None

    def test_priority_desc_fallback(self):
        """按 priority 降序遍历，高优先级失败后降级到低优先级。"""
        high = FakeFetcher(
            "high_eastmoney", priority=100, raise_exc=RuntimeError("boom")
        )
        low = FakeFetcher("low_tencent", priority=1, behavior="data")
        # 传入乱序，验证内部排序
        result = fetch_with_fallback([low, high], "600519")

        assert result == {"src": "low_tencent"}
        assert high.call_count == 1
        assert high.failure_count == 1
        assert low.call_count == 1
        assert low.success_count == 1

    def test_not_handled_falls_through(self):
        """NOT_HANDLED 换下一个源。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="not_handled")
        b = FakeFetcher("b_tencent", priority=5, behavior="data")

        result = fetch_with_fallback([a, b], "600519")

        assert result == {"src": "b_tencent"}
        assert a.success_count == 0
        assert b.success_count == 1

    def test_none_falls_through(self):
        """None 换下一个源。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="none")
        b = FakeFetcher("b_tencent", priority=5, behavior="data")

        result = fetch_with_fallback([a, b], "600519")

        assert result == {"src": "b_tencent"}

    def test_all_fail_returns_none(self):
        """所有源均失败 -> 返回 None。"""
        a = FakeFetcher("a_eastmoney", priority=10, raise_exc=RuntimeError("boom"))
        b = FakeFetcher("b_tencent", priority=5, raise_exc=RuntimeError("boom2"))

        result = fetch_with_fallback([a, b], "600519")

        assert result is None
        assert a.failure_count == 1
        assert b.failure_count == 1

    def test_rate_limit_error_falls_through_no_breaker(self):
        """RateLimitError(429) 换源，不计入熔断失败。"""
        a = FakeFetcher("a_eastmoney", priority=10, raise_exc=RateLimitError("u"))
        b = FakeFetcher("b_tencent", priority=5, behavior="data")

        result = fetch_with_fallback([a, b], "600519")

        assert result == {"src": "b_tencent"}
        assert a.failure_count == 0  # 429 不熔断
        assert b.success_count == 1

    def test_skips_unavailable_fetcher(self):
        """熔断 open 的 fetcher 被跳过。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="data")
        a.circuit_breaker.state = a.circuit_breaker.state.OPEN
        import time

        a.circuit_breaker.last_failure_time = time.time()
        a.circuit_breaker.failure_count = 99
        b = FakeFetcher("b_tencent", priority=5, behavior="data")

        result = fetch_with_fallback([a, b], "600519")

        assert result == {"src": "b_tencent"}
        assert a.call_count == 0

    def test_invalid_code_returns_none(self):
        """非法 code 返回 None。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="data")

        assert fetch_with_fallback([a], "bad code") is None
        assert a.call_count == 0


# ═══════════════════════════════════════════════════════════════
# NOT_HANDLED 序列化 / BaseFetcher provider 推断 / 边缘分支
# ═══════════════════════════════════════════════════════════════


class SequenceFetcher(FakeFetcher):
    """按动作序列依次执行的 fetcher（用于 429 重试路径）。"""

    def __init__(self, name, priority, actions):
        super().__init__(name, priority=priority, behavior="data")
        self.actions = list(actions)
        self._idx = 0

    def fetch(self, code="", **kwargs):
        self.call_count += 1
        act = self.actions[min(self._idx, len(self.actions) - 1)]
        self._idx += 1
        if act == "rate":
            raise RateLimitError("u")
        if act == "exc":
            raise RuntimeError("boom")
        if act == "none":
            return None
        return self.payload


class TestNotHandledPrimitives:
    """NOT_HANDLED 哨兵的 pickle / eq / hash 契约。"""

    def test_pickle_roundtrip(self):
        """pickle 往返返回同一单例（25/35 行：__reduce__ + _get_not_handled）。"""
        import pickle

        anew = pickle.loads(pickle.dumps(NOT_HANDLED))
        assert anew is NOT_HANDLED

    def test_eq_and_hash(self):
        """__eq__ 基于 isinstance，__hash__ 固定字符串（38/41 行）。"""
        from common.fetcher_base import _NotHandled

        assert NOT_HANDLED == NOT_HANDLED
        assert NOT_HANDLED == _NotHandled()
        assert NOT_HANDLED != "NOT_HANDLED"
        assert NOT_HANDLED != {"a": 1}
        assert hash(NOT_HANDLED) == hash("_NOT_HANDLED_")


class _ProviderFetcher(BaseFetcher):
    """仅用于测试 provider 显式/隐式推断解析。"""

    def __init__(self, name: str, provider: str | None = None):
        super().__init__(name, provider=provider)

    def fetch(self, code: str = "", **kwargs):
        return {"ok": 1}


class TestBaseFetcherProvider:
    """provider 推断三分支：显式 / 下划线 + 已知后缀 / 无下划线。"""

    def test_explicit_provider_wins(self):
        """provider 显式传入时优先（60 行）。"""
        f = _ProviderFetcher("odd_name", provider="custom")
        assert f.provider == "custom"

    def test_underscore_known_suffix_inferred(self):
        """name 含下划线且末段为已知 provider → 取末段（61-85 行）。"""
        f = _ProviderFetcher("northbound_flow_eastmoney")
        assert f.provider == "eastmoney"

    def test_underscore_unknown_suffix_uses_first(self):
        """末段非已知 provider → 取首段。"""
        f = _ProviderFetcher("quote_homebrew")
        assert f.provider == "quote"

    def test_name_without_underscore_uses_name(self):
        """无下划线的 name → provider = name（87 行）。"""
        f = _ProviderFetcher("solo")
        assert f.provider == "solo"

    def test_cb_config_load_exception(self, monkeypatch):
        """_load_cb_config 异常时回退默认熔断配置（118-120 行）。"""
        from config.loader import ConfigLoader

        def boom(*a, **k):
            raise RuntimeError("no data_source.yaml")

        monkeypatch.setattr(ConfigLoader, "load", classmethod(boom))
        f = _ProviderFetcher("x_eastmoney")
        assert f.circuit_breaker is not None
        assert f.circuit_breaker.failure_threshold == 5
        assert f.circuit_breaker.recovery_timeout == 60


# ═══════════════════════════════════════════════════════════════
# fetch_with_fallback 剩余分支
# ═══════════════════════════════════════════════════════════════


class TestFetchWithFallbackExtras:
    def test_invalid_code_multi_returns_none(self):
        """多源 + 非法 code → None（224 行：长度>1 分支的白名单防御）。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="data")
        b = FakeFetcher("b_tencent", priority=5, behavior="data")

        assert fetch_with_fallback([a, b], "bad code") is None
        assert a.call_count == 0
        assert b.call_count == 0

    def test_provider_in_backoff_skipped(self):
        """provider 在 429 退避窗口内被跳过（236-241 行）。"""
        from common.rate_limiter import get_rate_limiter

        a = FakeFetcher("a_eastmoney", priority=10, behavior="data")
        b = FakeFetcher("b_tencent", priority=5, behavior="data")
        get_rate_limiter().mark_429("eastmoney")

        result = fetch_with_fallback([a, b], "600519")

        assert result == {"src": "b_tencent"}
        assert a.call_count == 0  # eastmoney 退避中，未被调用
        assert b.call_count == 1


# ═══════════════════════════════════════════════════════════════
# DataFetcherManager 429 重试成功 / 重试异常 分支
# ═══════════════════════════════════════════════════════════════


class TestDataFetcherManager429Retry:
    def test_retry_success_stays_on_main_source(self):
        """429 后重试成功 → 返回主源数据（373-375 行）。"""
        a = SequenceFetcher("a_eastmoney", priority=10, actions=["rate", "data"])
        b = FakeFetcher("b_tencent", priority=5, behavior="data")
        mgr = DataFetcherManager([a, b])

        result = mgr.fetch("600519")

        assert result == {"src": "a_eastmoney"}
        assert a.call_count == 2
        assert b.call_count == 0  # 主源重试成功，未切到次源

    def test_retry_generic_exception_falls_to_next(self):
        """429 重试遇普通异常 → pass 后换源（378 行）。"""
        a = SequenceFetcher("a_eastmoney", priority=10, actions=["rate", "exc"])
        b = FakeFetcher("b_tencent", priority=5, behavior="data")
        mgr = DataFetcherManager([a, b])

        result = mgr.fetch("600519")

        assert result == {"src": "b_tencent"}
        assert a.call_count == 2
        assert b.call_count == 1


# ═══════════════════════════════════════════════════════════════
# fetch_with_cache_fallback 全分支
# ═══════════════════════════════════════════════════════════════


class TestDataFetcherManagerCacheFallback:
    """fetch_with_cache_fallback 的 fetch 命中 / 缓存命中 / 缓存损坏路径。"""

    def test_fetch_hit_returns_result(self):
        """fetch 成功直接返回（409-410 行）。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="data")
        mgr = DataFetcherManager([a])

        assert mgr.fetch_with_cache_fallback("600519") == {"src": "a_eastmoney"}

    def test_no_prefix_returns_fallback(self):
        """无 cache_prefix → 直接返回 fallback（411 行）。"""
        a = FakeFetcher("a_eastmoney", priority=10, behavior="none")
        mgr = DataFetcherManager([a])

        assert mgr.fetch_with_cache_fallback("600519", fallback="F") == "F"

    def test_cache_hit_returns_json(self, monkeypatch):
        """fetch None + 缓存命中 → json.loads 返回值（412-418 行）。"""
        import common.cache as cache_mod

        a = FakeFetcher("a_eastmoney", priority=10, behavior="none")
        mgr = DataFetcherManager([a])
        monkeypatch.setattr(cache_mod, "cache_key_for_stock", lambda *a, **k: "k")
        monkeypatch.setattr(cache_mod, "get", lambda key, ttl: b'{"v": 1}')

        assert mgr.fetch_with_cache_fallback("600519", cache_prefix="pfx") == {"v": 1}

    def test_cache_miss_returns_fallback(self, monkeypatch):
        """fetch None + 缓存未命中 → fallback（414 行）。"""
        import common.cache as cache_mod

        a = FakeFetcher("a_eastmoney", priority=10, behavior="none")
        mgr = DataFetcherManager([a])
        monkeypatch.setattr(cache_mod, "cache_key_for_stock", lambda *a, **k: "k")
        monkeypatch.setattr(cache_mod, "get", lambda key, ttl: None)

        assert (
            mgr.fetch_with_cache_fallback("600519", cache_prefix="pfx", fallback="F")
            == "F"
        )

    def test_cache_corrupt_returns_fallback(self, monkeypatch, caplog):
        """缓存损坏（非 JSON）→ warning + fallback（419-420 行）。"""
        import logging

        import common.cache as cache_mod

        a = FakeFetcher("a_eastmoney", priority=10, behavior="none")
        mgr = DataFetcherManager([a])
        monkeypatch.setattr(cache_mod, "cache_key_for_stock", lambda *a, **k: "k")
        monkeypatch.setattr(cache_mod, "get", lambda key, ttl: b"not-json")

        with caplog.at_level(logging.WARNING, logger="common.fetcher_base"):
            result = mgr.fetch_with_cache_fallback(
                "600519", cache_prefix="pfx", fallback="F"
            )

        assert result == "F"
        assert "缓存数据损坏" in caplog.text
