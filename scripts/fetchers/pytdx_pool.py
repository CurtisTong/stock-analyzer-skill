"""pytdx 进程级连接池，复用 TdxHq_API 连接。"""

import logging
import threading
import time

logger = logging.getLogger(__name__)

try:
    from pytdx.hq import TdxHq_API

    HAS_PYTDX = True
except ImportError:
    HAS_PYTDX = False


class TdxPool:
    """线程安全的 pytdx 连接池。

    Args:
        servers: (host, port) 列表，用于新建连接时轮询。
        size: 池最大连接数。
        idle_timeout: 空闲连接超时秒数，超时连接会被丢弃。
    """

    def __init__(
        self, servers: list[tuple[str, int]], size: int = 4, idle_timeout: int = 30
    ):
        self.servers = servers
        self.size = size
        self.idle_timeout = idle_timeout
        self._lock = threading.Lock()
        # 每项: {"api": TdxHq_API, "host": str, "port": int, "idle_since": float}
        self._pool: list[dict] = []
        self._server_idx = 0

    def get(self) -> tuple:
        """从池中获取一个可用连接。

        Returns:
            (api, host, port) 三元组；调用方负责在使用后调用 put()。

        Raises:
            RuntimeError: 所有服务器均不可用。
        """
        with self._lock:
            # 1. 尝试复用空闲连接
            now = time.time()
            while self._pool:
                entry = self._pool.pop(0)
                if now - entry["idle_since"] <= self.idle_timeout:
                    logger.debug(
                        "pytdx_pool 复用连接 %s:%s", entry["host"], entry["port"]
                    )
                    return entry["api"], entry["host"], entry["port"]
                # 超时，关闭
                self._close(entry["api"])

        # 2. 池中无可用连接，新建
        api, host, port = self._connect_new()
        return api, host, port

    def put(self, api, host: str = "", port: int = 0):
        """归还连接到池。超过池上限则直接关闭。"""
        with self._lock:
            if len(self._pool) < self.size:
                self._pool.append(
                    {
                        "api": api,
                        "host": host,
                        "port": port,
                        "idle_since": time.time(),
                    }
                )
                logger.debug(
                    "pytdx_pool 归还连接 %s:%s，池大小 %d", host, port, len(self._pool)
                )
            else:
                self._close(api)

    def close_all(self):
        """关闭池中所有连接。"""
        with self._lock:
            for entry in self._pool:
                self._close(entry["api"])
            self._pool.clear()

    def _connect_new(self):
        """轮询服务器列表，返回第一个成功连接。"""
        for i in range(len(self.servers)):
            idx = (self._server_idx + i) % len(self.servers)
            host, port = self.servers[idx]
            try:
                api = TdxHq_API()
                api.connect(host, port, time_out=5)
                self._server_idx = (idx + 1) % len(self.servers)
                logger.debug("pytdx_pool 新建连接 %s:%s", host, port)
                return api, host, port
            except Exception as e:
                logger.debug("pytdx_pool 连接 %s:%s 失败: %s", host, port, e)
        raise RuntimeError("pytdx_pool: 所有服务器均不可用")

    @staticmethod
    def _close(api):
        """安全关闭连接。"""
        try:
            api.disconnect()
        except Exception as e:
            logger.debug("pytdx 断开连接失败: %s", e)


# 模块级默认池实例（惰性初始化）
_default_pool: TdxPool | None = None
_default_pool_lock = threading.Lock()


def get_default_pool(servers: list[tuple[str, int]], **kwargs) -> TdxPool:
    """获取或创建模块级默认连接池。"""
    global _default_pool
    with _default_pool_lock:
        if _default_pool is None:
            _default_pool = TdxPool(servers, **kwargs)
        return _default_pool
