"""LazyFetcherRegistry 单元测试。

验证 lazy_registry.py 中 LazyFetcherRegistry 的延迟加载、缓存、
线程安全双重检查锁（DCL）、reset 及异常处理行为。
"""

import threading
import pytest
from unittest.mock import MagicMock

from common.lazy_registry import LazyFetcherRegistry


def _make_fetcher(name):
    """构造带 name 属性的 mock fetcher。"""
    f = MagicMock()
    f.name = name
    return f


class TestGetAllLazyLoad:
    """TC-1: get_all() 首次调用触发 import_func，返回 fetcher 列表。"""

    def test_first_call_triggers_import(self):
        fetchers = [_make_fetcher("margin_east"), _make_fetcher("flow_sina")]
        import_func = MagicMock(return_value=fetchers)
        reg = LazyFetcherRegistry(import_func)

        result = reg.get_all()

        assert result is fetchers
        import_func.assert_called_once()

    def test_get_all_returns_cached_list_object(self):
        """返回的列表是同一个对象（缓存）。"""
        fetchers = [_make_fetcher("margin_east")]
        import_func = MagicMock(return_value=fetchers)
        reg = LazyFetcherRegistry(import_func)

        r1 = reg.get_all()
        r2 = reg.get_all()

        assert r1 is fetchers
        assert r2 is fetchers


class TestGetAllCached:
    """TC-2: get_all() 第二次调用不触发 import_func（缓存命中）。"""

    def test_second_call_no_import(self):
        fetchers = [_make_fetcher("margin_east")]
        import_func = MagicMock(return_value=fetchers)
        reg = LazyFetcherRegistry(import_func)

        reg.get_all()
        reg.get_all()
        reg.get_all()

        assert import_func.call_count == 1


class TestFindByPrefix:
    """TC-3: find() 按前缀查找返回正确 fetcher。"""

    def test_find_by_prefix_returns_first_match(self):
        f1 = _make_fetcher("margin_east")
        f2 = _make_fetcher("flow_sina")
        f3 = _make_fetcher("margin_sinajs")
        reg = LazyFetcherRegistry(MagicMock(return_value=[f1, f2, f3]))

        result = reg.find("margin")

        assert result is f1  # 返回第一个匹配

    def test_find_exact_name_matches(self):
        f1 = _make_fetcher("margin_east")
        reg = LazyFetcherRegistry(MagicMock(return_value=[f1]))

        result = reg.find("margin_east")

        assert result is f1


class TestFindNotFound:
    """TC-4: find() 找不到返回 None。"""

    def test_find_no_match_returns_none(self):
        f1 = _make_fetcher("margin_east")
        reg = LazyFetcherRegistry(MagicMock(return_value=[f1]))

        result = reg.find("nonexistent")

        assert result is None


class TestReset:
    """TC-5: reset() 后缓存清空，下次 get_all() 重新调用 import_func。"""

    def test_reset_clears_cache(self):
        fetchers = [_make_fetcher("margin_east")]
        import_func = MagicMock(return_value=fetchers)
        reg = LazyFetcherRegistry(import_func)

        reg.get_all()
        assert import_func.call_count == 1

        reg.reset()

        fetchers2 = [_make_fetcher("margin_east")]
        import_func.return_value = fetchers2
        result = reg.get_all()

        assert result is fetchers2
        assert import_func.call_count == 2


class TestConcurrentGetAll:
    """TC-6: 多线程并发 get_all() 只调用一次 import_func（DCL）。"""

    def test_concurrent_get_all_single_import(self):
        fetchers = [_make_fetcher("margin_east")]
        call_count = 0
        lock = threading.Lock()

        def import_func():
            nonlocal call_count
            with lock:
                call_count += 1
            # 模拟慢加载，增加竞态窗口
            import time
            time.sleep(0.05)
            return fetchers

        reg = LazyFetcherRegistry(import_func)
        barrier = threading.Barrier(20)
        results = []

        def worker():
            barrier.wait()
            results.append(reg.get_all())

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert call_count == 1
        assert all(r is fetchers for r in results)
        assert len(results) == 20


class TestImportFuncException:
    """TC-7: import_func 抛异常时不缓存，下次仍调用。"""

    def test_exception_not_cached(self):
        import_func = MagicMock(side_effect=RuntimeError("import failed"))
        reg = LazyFetcherRegistry(import_func)

        # 第一次调用抛异常
        with pytest.raises(RuntimeError):
            reg.get_all()

        # 第二次调用仍然触发 import_func（未缓存）
        with pytest.raises(RuntimeError):
            reg.get_all()

        assert import_func.call_count == 2

    def test_exception_then_success(self):
        fetchers = [_make_fetcher("margin_east")]
        import_func = MagicMock(
            side_effect=[RuntimeError("transient"), fetchers]
        )
        reg = LazyFetcherRegistry(import_func)

        with pytest.raises(RuntimeError):
            reg.get_all()

        result = reg.get_all()
        assert result is fetchers
        assert import_func.call_count == 2

        # 成功后缓存
        reg.get_all()
        assert import_func.call_count == 2


class TestEmptyListFind:
    """TC-8: 空 fetcher 列表的 find() 返回 None。"""

    def test_empty_list_find_returns_none(self):
        reg = LazyFetcherRegistry(MagicMock(return_value=[]))

        result = reg.find("anything")

        assert result is None

    def test_empty_list_get_all_returns_empty(self):
        reg = LazyFetcherRegistry(MagicMock(return_value=[]))

        result = reg.get_all()

        assert result == []
