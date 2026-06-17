"""common/__init__.py 懒加载测试。"""

import sys
import pickle


def test_lazy_import_to_float():
    """from common import to_float 应能正常工作。"""
    from common import to_float

    assert to_float("3.14") == 3.14
    assert to_float(None) == 0.0


def test_lazy_import_http_get():
    """from common import http_get 应能正常工作。"""
    from common import http_get

    assert callable(http_get)


def test_lazy_import_cache_get():
    """from common import cache_get 应能正常工作。"""
    from common import cache_get

    assert callable(cache_get)


def test_data_manager_last_error():
    """DataFetcherManager.fetch() 失败后 last_error 应可访问。"""
    from common import DataFetcherManager, BaseFetcher

    class FailFetcher(BaseFetcher):
        def __init__(self):
            super().__init__("test_fail", priority=1)

        def fetch(self, code, **kwargs):
            raise ValueError("test error")

    mgr = DataFetcherManager([FailFetcher()])
    result = mgr.fetch("sh600519")
    assert result is None
    assert mgr.last_error is not None
    assert "test error" in str(mgr.last_error)


def test_not_handled_pickle():
    """NOT_HANDLED 应可 pickle 序列化并恢复单例。"""
    from common import NOT_HANDLED

    data = pickle.dumps(NOT_HANDLED)
    restored = pickle.loads(data)
    assert restored is NOT_HANDLED


def test_base_fetcher_provider():
    """BaseFetcher 应有 provider 属性。"""
    from common import BaseFetcher

    class TestFetcher(BaseFetcher):
        def fetch(self, code, **kwargs):
            return None

    f = TestFetcher("tencent_quote", priority=5)
    assert f.provider == "tencent"
    assert f.name == "tencent_quote"


def test_backward_compat_aliases():
    """向后兼容别名应可用。"""
    from common import (
        DataSourceUnavailableError,
        DataParseError,
        NetworkError,
        ParseError,
    )

    assert DataSourceUnavailableError is NetworkError
    assert DataParseError is ParseError


def test_all_exports_present():
    """__all__ 中的所有符号都应可导入。"""
    import common

    for name in common.__all__:
        obj = getattr(common, name)
        assert obj is not None, f"common.{name} 为 None"


def test_circuit_breaker_still_works():
    """熔断器应正常工作。"""
    from common import CircuitBreaker, CircuitState

    cb = CircuitBreaker("test_cb", failure_threshold=2, recovery_timeout=1)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
