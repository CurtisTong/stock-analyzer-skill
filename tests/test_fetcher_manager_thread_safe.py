"""Fetcher 管理器线程安全测试。"""

import threading
from fetchers import get_quote_manager, get_kline_manager


def test_get_quote_manager_returns_same_instance():
    """多线程调用 get_quote_manager 应返回同一实例。"""
    results = []
    errors = []

    def get_it():
        try:
            results.append(id(get_quote_manager()))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=get_it) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"错误: {errors}"
    assert len(set(results)) == 1, f"返回了 {len(set(results))} 个不同实例"


def test_get_kline_manager_returns_same_instance():
    """get_kline_manager 也应返回同一实例。"""
    m1 = get_kline_manager()
    m2 = get_kline_manager()
    assert m1 is m2
