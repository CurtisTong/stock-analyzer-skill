"""pytdx 本地服务探活模块。

pytdx 需要本机（或局域网）运行通达信行情服务（默认 127.0.0.1:7709）。
绝大多数用户机器上并没有这个服务，而 pytdx 的连接池会依次尝试
8 个服务器 × 5s 超时（最坏 ~40s 阻塞），且熔断器在"吞异常"实现下
永远不会开启——每次请求都重复这段阻塞。

本模块用 TCP 探测（不建 pytdx 连接、不发协议请求）判断本地服务是否
可用，把"服务不在"和"服务在但请求失败"区分开：
- 服务不可用 → 源直接跳过，不进入降级链（不是数据源故障，是环境缺能力）
- 服务可用   → 正常走熔断/退避

探活结果带 TTL 缓存（默认 5 分钟），避免每次请求都探测。
"""

from __future__ import annotations

import logging
import socket
import time

logger = logging.getLogger(__name__)

# 探活结果缓存（进程级，TTL 秒）
_PROBE_CACHE: dict[str, tuple[float, bool]] = {}
_PROBE_TTL = 300  # 5 分钟

# 探测超时（秒）——TCP connect 到本机端口，超过即视为不可用
_PROBE_TIMEOUT = 0.5


def _get_cached(host: str, port: int) -> bool | None:
    """读取未过期的缓存结果。"""
    entry = _PROBE_CACHE.get(f"{host}:{port}")
    if entry and (time.time() - entry[0]) < _PROBE_TTL:
        return entry[1]
    return None


def _set_cached(host: str, port: int, ok: bool) -> None:
    _PROBE_CACHE[f"{host}:{port}"] = (time.time(), ok)


def reset_probe_cache() -> None:
    """重置探活缓存（测试用）。"""
    _PROBE_CACHE.clear()


def probe_tdx_server(host: str, port: int, timeout: float = _PROBE_TIMEOUT) -> bool:
    """TCP 探测通达信服务端口是否可连。

    Args:
        host: 服务地址
        port: 服务端口
        timeout: 连接超时（秒）

    Returns:
        True 表示端口可连（服务可能在运行）
    """
    cached = _get_cached(host, port)
    if cached is not None:
        return cached
    try:
        with socket.create_connection((host, port), timeout=timeout):
            ok = True
    except OSError:
        ok = False
    _set_cached(host, port, ok)
    if not ok:
        logger.debug("pytdx 探活: %s:%s 不可连", host, port)
    return ok


def any_server_available(servers, timeout: float = _PROBE_TIMEOUT) -> bool:
    """任一服务器可连即视为 pytdx 可用。

    Args:
        servers: (host, port) 列表
        timeout: 单次探测超时（秒）

    Returns:
        True 表示至少一个服务端口可连
    """
    for host, port in servers or ():
        if probe_tdx_server(host, port, timeout):
            return True
    return False
