"""2026-11-21 code review HTTP 修复回归。

- P1-4(§3.1 #4)：响应超限截断后连接不得回池（残留字节污染）；
- P2 #4(§4.1)：requests.Session 改为 thread-local，撤回"线程安全"过度承诺；
- P2 #5(§4.1)：max_retries 透传并据此构造 Retry，两条路径语义一致。
"""

from __future__ import annotations

import threading

import pytest

import common.http as http


@pytest.fixture(autouse=True)
def _reset_thread_local():
    """会话按线程存放，测试间清空主线程的缓存。"""
    http._thread_local.__dict__.clear()
    yield
    http._thread_local.__dict__.clear()


class _FakeResponse:
    def __init__(self, chunks, status: int = 200):
        self._chunks = iter(chunks)
        self.status = status

    def read(self, _size=-1):
        return next(self._chunks, b"")

    def getheader(self, _name):
        return None


class _FakeConn:
    def __init__(self, response):
        self.response = response
        self.closed = False

    def request(self, *_args, **_kwargs):
        return None

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class TestP1ConnectionPollution:
    """P1-4：超限响应必须丢弃连接，不能带着未读字节回池。"""

    def test_truncated_response_connection_is_discarded(self, monkeypatch):
        monkeypatch.setattr(http, "MAX_RESPONSE_SIZE", 10)
        conn = _FakeConn(_FakeResponse([b"0123456789", b"EXTRA-UNREAD"]))
        monkeypatch.setattr(http, "_get_connection", lambda *_a, **_k: conn)
        returned = []
        monkeypatch.setattr(http, "_return_connection", lambda key, c: returned.append(c))

        result = http._http_get_internal("http://example.com/data", max_retries=1)

        assert result == b"0123456789", "截断内容仍应返回（公开行为不变）"
        assert conn.closed is True, "残留未读字节的连接必须关闭"
        assert returned == [], "截断连接绝不能归还连接池"

    def test_normal_response_connection_still_returned(self, monkeypatch):
        monkeypatch.setattr(http, "MAX_RESPONSE_SIZE", 100)
        conn = _FakeConn(_FakeResponse([b"ok"]))
        monkeypatch.setattr(http, "_get_connection", lambda *_a, **_k: conn)
        returned = []
        monkeypatch.setattr(http, "_return_connection", lambda key, c: returned.append(c))

        result = http._http_get_internal("http://example.com/data", max_retries=1)

        assert result == b"ok"
        assert returned == [conn], "正常响应仍要回池复用"


@pytest.mark.skipif(not http._HAS_REQUESTS, reason="requests 未安装")
class TestP2ThreadLocalSession:
    """P2 #4：Session 线程私有，不再进程级共享。"""

    def test_session_is_thread_local(self):
        main_session = http._get_session(3)
        box: dict = {}

        def worker():
            box["session"] = http._get_session(3)

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=5)

        assert "session" in box
        assert box["session"] is not main_session, "不同线程不应共享同一个 Session"
        assert http._get_session(3) is main_session, "同线程重复获取应复用"


@pytest.mark.skipif(not http._HAS_REQUESTS, reason="requests 未安装")
class TestP2MaxRetriesPassthrough:
    """P2 #5：max_retries 不再被硬编码的 Retry(total=3) 吞掉。"""

    def test_retry_built_from_max_retries(self):
        session5 = http._get_session(5)
        session1 = http._get_session(1)
        adapter5 = session5.get_adapter("https://example.com")
        adapter1 = session1.get_adapter("https://example.com")
        # max_retries 语义 = 总尝试次数；urllib3 total = 首尝试之外的重试次数
        assert adapter5.max_retries.total == 4
        assert adapter1.max_retries.total == 0

    def test_http_get_forwards_max_retries(self, monkeypatch):
        seen: dict = {}

        def fake_requests_get(url, headers=None, timeout=10, max_retries=3):
            seen["max_retries"] = max_retries
            return b"ok"

        monkeypatch.setattr(http, "_http_get_requests", fake_requests_get)
        assert http.http_get("http://example.com", max_retries=7) == b"ok"
        assert seen["max_retries"] == 7

    def test_http_get_with_headers_forwards_max_retries(self, monkeypatch):
        seen: dict = {}

        def fake_requests_get(url, headers=None, timeout=10, max_retries=3):
            seen["max_retries"] = max_retries
            return b"ok"

        monkeypatch.setattr(http, "_http_get_requests", fake_requests_get)
        assert http.http_get_with_headers("http://example.com", max_retries=6) == b"ok"
        assert seen["max_retries"] == 6

    def test_stdlib_path_uses_max_retries_when_requests_missing(self, monkeypatch):
        seen: dict = {}

        def fake_internal(url, headers=None, timeout=10, max_retries=3):
            seen["max_retries"] = max_retries
            return b"ok"

        monkeypatch.setattr(http, "_HAS_REQUESTS", False)
        monkeypatch.setattr(http, "_http_get_internal", fake_internal)
        http.http_get("http://example.com", max_retries=7)
        assert seen["max_retries"] == 7, "requests 缺失时 stdlib 路径也必须消费 max_retries"
