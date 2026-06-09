"""HTTP 客户端：GET 请求、重试、编码转换。"""
import random
import time
import urllib.request
import urllib.error

from common.exceptions import RateLimitError, NetworkError

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "stock-analyzer-skill/1.0",
]


def http_get(url: str, timeout: int = 10, max_retries: int = 3) -> bytes:
    """GET 请求，指数退避重试，UA 随机轮换。429 立即抛出不重试。"""
    last_err = None
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers={
            "User-Agent": random.choice(USER_AGENTS),
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                raise RateLimitError(url)
            if attempt < max_retries - 1:
                delay = min(1.0 * (2 ** attempt), 8.0)
                jitter = random.uniform(0, delay * 0.5)
                time.sleep(delay + jitter)
        except (urllib.error.URLError, TimeoutError, OSError, ConnectionResetError, BrokenPipeError) as e:
            last_err = e
            if attempt < max_retries - 1:
                delay = min(1.0 * (2 ** attempt), 8.0)
                jitter = random.uniform(0, delay * 0.5)
                time.sleep(delay + jitter)
    raise NetworkError(url, str(last_err), max_retries)


def http_get_with_headers(url: str, headers: dict = None, timeout: int = 10, max_retries: int = 3) -> bytes:
    """带自定义 headers 的 GET 请求（用于新浪等需要 Referer 的源）。"""
    last_err = None
    req_headers = {"User-Agent": random.choice(USER_AGENTS)}
    if headers:
        req_headers.update(headers)
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers=req_headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                raise RateLimitError(url)
            if attempt < max_retries - 1:
                delay = min(1.0 * (2 ** attempt), 8.0)
                jitter = random.uniform(0, delay * 0.5)
                time.sleep(delay + jitter)
        except (urllib.error.URLError, TimeoutError, OSError, ConnectionResetError, BrokenPipeError) as e:
            last_err = e
            if attempt < max_retries - 1:
                delay = min(1.0 * (2 ** attempt), 8.0)
                jitter = random.uniform(0, delay * 0.5)
                time.sleep(delay + jitter)
    raise NetworkError(url, str(last_err), max_retries)


def decode_gbk(data: bytes) -> str:
    """腾讯接口 GBK → UTF-8。"""
    return data.decode("gbk", errors="replace")


__all__ = [
    "USER_AGENTS", "http_get", "http_get_with_headers", "decode_gbk",
]
