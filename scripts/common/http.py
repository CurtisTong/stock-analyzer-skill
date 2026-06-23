"""HTTP 客户端：GET 请求、重试、编码转换、连接池复用。

优先使用 requests（可选依赖，连接池复用 + 自动编码），
缺失时降级为 http.client（stdlib）。
"""

import http.client
import logging
import random
import socket
import threading
import time
import urllib.parse

logger = logging.getLogger(__name__)

# 尝试导入 requests（可选依赖）
try:
    import requests as _requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

from common.exceptions import RateLimitError, NetworkError

# ---------- requests 连接池（可选） ----------

_session = None
_session_lock = threading.Lock()


def _get_session():
    """获取或创建 requests Session（线程安全，连接池复用）。"""
    global _session
    if _session is not None:
        return _session
    with _session_lock:
        if _session is not None:
            return _session
        _session = _requests.Session()
        retry = Retry(
            total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504]
        )
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=32,
            pool_maxsize=32,
        )
        _session.mount("http://", adapter)
        _session.mount("https://", adapter)
        _session.headers.update({"User-Agent": "stock-analyzer-skill/1.0"})
        return _session


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "stock-analyzer-skill/1.0",
]

MAX_POOL_SIZE = 32

# ---------- 连接池（keep-alive 复用） ----------

_connection_pool: dict[str, list[http.client.HTTPConnection]] = {}
_pool_lock = threading.Lock()


def _pool_key(url: str) -> str:
    """从 URL 提取连接池键。"""
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme or "https"
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if scheme == "https" else 80)
    return f"{scheme}://{host}:{port}"


def _create_connection(url: str, timeout: int = 10) -> http.client.HTTPConnection:
    """创建新连接。"""
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme or "https"
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if scheme == "https" else 80)
    if scheme == "https":
        return http.client.HTTPSConnection(host, port=port, timeout=timeout)
    return http.client.HTTPConnection(host, port=port, timeout=timeout)


def _get_connection(url: str, timeout: int = 10) -> http.client.HTTPConnection:
    """从连接池获取或创建连接（线程安全，同一 host 可复用多个连接）。"""
    key = _pool_key(url)
    with _pool_lock:
        conns = _connection_pool.get(key, [])
        # 找到一个仍然存活的连接
        while conns:
            conn = conns.pop()
            if hasattr(conn, "sock") and conn.sock is not None:
                return conn
        # 池中无可用连接
        pass
    return _create_connection(url, timeout)


def _return_connection(url: str, conn: http.client.HTTPConnection) -> None:
    """将连接归还到连接池，池满时 close。同一 host 保留多个连接。"""
    key = _pool_key(url)
    with _pool_lock:
        conns = _connection_pool.get(key)
        if conns is None:
            _connection_pool[key] = [conn]
        elif len(conns) < MAX_POOL_SIZE:
            conns.append(conn)
        else:
            try:
                conn.close()
            except Exception as e:
                logger.debug("关闭溢出连接失败: %s", e)


def _do_request(
    conn: http.client.HTTPConnection,
    url: str,
    headers: dict[str, str],
    timeout: int,
) -> bytes:
    """执行一次 HTTP GET，返回响应体。处理非 2xx 状态码。"""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    conn.request("GET", path, headers=headers)
    resp = conn.getresponse()
    status = resp.status

    if status == 429:
        retry_after_header = resp.getheader("Retry-After")
        try:
            resp.read()
        except Exception as e:
            logger.debug("读取 429 响应体失败: %s", e)
        raise RateLimitError(
            url,
            retry_after=int(retry_after_header) if retry_after_header else None,
        )

    if status >= 400:
        try:
            resp.read()
        except Exception as e:
            logger.debug("读取 HTTP %d 响应体失败: %s", status, e)
        raise http.client.HTTPException(f"HTTP {status} for {url}")

    return resp.read()


def _invalidate_connection(url: str, conn: http.client.HTTPConnection) -> None:
    """关闭失效连接。"""
    try:
        conn.close()
    except Exception as e:
        logger.debug("关闭失效连接失败: %s", e)


def _http_get_internal(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = 10,
    max_retries: int = 3,
) -> bytes:
    """内部 GET 实现：指数退避重试，连接池复用。429 立即抛出不重试。"""
    req_headers = {"User-Agent": random.choice(USER_AGENTS)}
    if headers:
        req_headers.update(headers)
    last_err = None
    conn = None

    for attempt in range(max_retries):
        try:
            if conn is None:
                conn = _get_connection(url, timeout)
            result = _do_request(conn, url, req_headers, timeout)
            _return_connection(url, conn)
            return result
        except RateLimitError:
            raise
        except (
            http.client.HTTPException,
            socket.error,
            OSError,
            ConnectionResetError,
            BrokenPipeError,
        ) as e:
            last_err = e
            if conn is not None:
                _invalidate_connection(url, conn)
                conn = None
            if attempt < max_retries - 1:
                delay = min(1.0 * (2**attempt), 8.0)
                jitter = random.uniform(0, delay * 0.5)
                time.sleep(delay + jitter)

    raise NetworkError(url, str(last_err), max_retries)


def _http_get_requests(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = 10,
) -> bytes:
    """requests 版本的 GET 请求（连接池复用 + 自动编码）。"""
    session = _get_session()
    req_headers = {}
    if headers:
        req_headers.update(headers)

    resp = session.get(url, headers=req_headers, timeout=timeout)

    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After")
        raise RateLimitError(url, retry_after=int(retry_after) if retry_after else None)

    resp.raise_for_status()
    return resp.content


def http_get(url: str, timeout: int = 10, max_retries: int = 3) -> bytes:
    """GET 请求，指数退避重试，连接池复用。429 立即抛出不重试。

    优先使用 requests（可选依赖），缺失时降级为 http.client。
    """
    if _HAS_REQUESTS:
        try:
            return _http_get_requests(url, timeout=timeout)
        except RateLimitError:
            raise
        except Exception as e:
            logger.debug("requests 请求失败，降级到 http.client: %s", e)
    return _http_get_internal(
        url, headers=None, timeout=timeout, max_retries=max_retries
    )


def http_get_with_headers(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = 10,
    max_retries: int = 3,
) -> bytes:
    """带自定义 headers 的 GET 请求（用于新浪等需要 Referer 的源）。"""
    if _HAS_REQUESTS:
        try:
            return _http_get_requests(url, headers=headers, timeout=timeout)
        except RateLimitError:
            raise
        except Exception as e:
            logger.debug("requests 请求失败，降级到 http.client: %s", e)
    return _http_get_internal(
        url, headers=headers, timeout=timeout, max_retries=max_retries
    )


def decode_gbk(data: bytes) -> str:
    """腾讯接口 GBK → UTF-8。"""
    return data.decode("gbk", errors="replace")


__all__ = [
    "USER_AGENTS",
    "MAX_POOL_SIZE",
    "http_get",
    "http_get_with_headers",
    "decode_gbk",
]
