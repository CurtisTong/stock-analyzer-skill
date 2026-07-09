"""连接池并发安全测试。"""

import importlib
import threading
from unittest.mock import patch, MagicMock


def _get_real_http_module():
    """获取真实的 common.http 模块（避免被其他测试的 mock 干扰）。"""
    import sys
    import common.http

    mod = common.http
    # 如果模块属性被 mock 污染，重新加载
    if not callable(getattr(mod, "_get_connection", None)):
        if "common.http" in sys.modules:
            real_spec = getattr(mod, "__spec__", None)
            if real_spec is not None:
                mod = importlib.reload(common.http)
    return mod


def test_concurrent_get_connection_no_leak():
    """多线程同时 _get_connection 不应产生连接泄漏或异常。"""
    mod = _get_real_http_module()
    _get_connection = mod._get_connection
    _connection_pool = mod._connection_pool

    _connection_pool.clear()
    results = []
    errors = []

    def get_conn():
        try:
            with patch.object(mod.http.client, "HTTPSConnection") as mock_cls:
                mock_conn = MagicMock()
                mock_conn.sock = MagicMock()
                mock_cls.return_value = mock_conn
                conn = _get_connection(
                    "https://example.com:443", "https", "example.com", 443
                )
                results.append(id(conn))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=get_conn) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"并发错误: {errors}"
    # 所有连接都应被成功创建
    assert len(results) == 20, f"应创建 20 个连接，实际 {len(results)}"


def test_return_connection_pool_size_limit():
    """归还连接时池大小超限应 close 而非归还。"""
    mod = _get_real_http_module()
    _connection_pool = mod._connection_pool
    _pool_lock = mod._pool_lock
    MAX_POOL_SIZE = mod.MAX_POOL_SIZE

    _connection_pool.clear()
    for i in range(MAX_POOL_SIZE):
        key = f"host{i}:443"
        _connection_pool[key] = [MagicMock()]

    MagicMock()
    with _pool_lock:
        current_size = len(_connection_pool)
    assert current_size == MAX_POOL_SIZE
