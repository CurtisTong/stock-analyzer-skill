"""pytdx 连接池单元测试。"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

# 模拟 pytdx 模块（测试环境不安装 pytdx）
mock_tdx_api_cls = MagicMock()
mock_tdx_hq = MagicMock()
mock_tdx_hq.TdxHq_API = mock_tdx_api_cls
mock_tdx = MagicMock()
mock_tdx.hq = mock_tdx_hq

with patch.dict("sys.modules", {"pytdx": mock_tdx, "pytdx.hq": mock_tdx_hq}):
    from fetchers._common import pytdx_pool as _pool_mod
    from fetchers._common.pytdx_pool import TdxPool


class TestTdxPool:
    """连接池核心功能测试。"""

    def _make_pool(self, size=4, idle_timeout=30):
        servers = [("127.0.0.1", 7709), ("127.0.0.2", 7709)]
        return TdxPool(servers, size=size, idle_timeout=idle_timeout)

    def test_get_creates_new_connection(self):
        """池为空时 get() 应新建连接。"""
        mock_api = MagicMock()
        mock_tdx_api_cls.reset_mock()
        mock_tdx_api_cls.return_value = mock_api

        pool = self._make_pool()
        api, host, port = pool.get()

        assert api is mock_api
        mock_api.connect.assert_called_once()

    def test_put_and_get_reuses(self):
        """归还后再 get() 应复用连接。"""
        mock_api = MagicMock()
        mock_tdx_api_cls.reset_mock()
        mock_tdx_api_cls.return_value = mock_api

        pool = self._make_pool()
        api, host, port = pool.get()
        pool.put(api, host, port)

        assert len(pool._pool) == 1

        api2, _, _ = pool.get()
        assert api2 is api  # 复用同一个对象

    def test_put_excess_closes(self):
        """池满时 put() 应关闭连接。"""
        mock_api = MagicMock()
        mock_tdx_api_cls.reset_mock()
        mock_tdx_api_cls.return_value = mock_api

        pool = self._make_pool(size=1)
        api1, h1, p1 = pool.get()
        pool.put(api1, h1, p1)

        api2, h2, p2 = pool.get()
        pool.put(api2, h2, p2)

        assert len(pool._pool) <= 1

    def test_idle_timeout_evicts(self):
        """超时连接应被丢弃。"""
        mock_api = MagicMock()
        mock_tdx_api_cls.reset_mock()
        mock_tdx_api_cls.return_value = mock_api

        pool = self._make_pool(idle_timeout=1)
        api, host, port = pool.get()
        pool.put(api, host, port)

        # 伪造空闲时间
        pool._pool[0]["idle_since"] = time.time() - 2

        api2, _, _ = pool.get()
        # 超时连接被丢弃，应新建
        assert mock_tdx_api_cls.call_count == 2

    def test_close_all(self):
        """close_all() 应关闭所有连接并清空池。"""
        mock_api = MagicMock()
        mock_tdx_api_cls.reset_mock()
        mock_tdx_api_cls.return_value = mock_api

        pool = self._make_pool()
        api, host, port = pool.get()
        pool.put(api, host, port)

        pool.close_all()
        assert len(pool._pool) == 0
        api.disconnect.assert_called_once()

    def test_get_connect_failure_raises(self):
        """所有服务器不可用时应抛出 RuntimeError。"""
        mock_tdx_api_cls.return_value = MagicMock()
        mock_tdx_api_cls.return_value.connect.side_effect = ConnectionError("fail")

        pool = self._make_pool()
        with pytest.raises(RuntimeError, match="所有服务器均不可用"):
            pool.get()

    def test_server_rotation(self):
        """连续新建连接应轮询不同服务器。"""
        mock_api = MagicMock()
        mock_tdx_api_cls.reset_mock()
        mock_tdx_api_cls.return_value = mock_api

        pool = self._make_pool()
        _, h1, p1 = pool.get()
        _, h2, p2 = pool.get()

        calls = mock_api.connect.call_args_list
        assert len(calls) == 2
        assert calls[0] != calls[1]
