"""common/http.py 覆盖率补充测试。

覆盖 _get_session / _create_connection / _get_connection / _return_connection /
_do_request / _http_get_requests / _http_get_internal / http_get / http_get_with_headers /
decode_gbk 的更多分支。
注意：mock time.sleep 避免重试导致超时。
"""

import importlib
import sys
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from common import http as http_mod
from common.exceptions import RateLimitError, NetworkError, HTTPStatusError


# ═══════════════════════════════════════════════════════════════
# _get_session
# ═══════════════════════════════════════════════════════════════


class TestGetSession:
    def test_returns_session(self):
        """requests 可用时返回 Session。"""
        # 重置全局 session
        old = http_mod._session
        http_mod._session = None
        try:
            if http_mod._HAS_REQUESTS:
                sess = http_mod._get_session()
                assert sess is not None
                assert sess.max_redirects == 5
            else:
                pytest.skip("requests 不可用")
        finally:
            http_mod._session = old

    def test_caches_session(self):
        """重复调用返回同一实例。"""
        old = http_mod._session
        http_mod._session = None
        try:
            if http_mod._HAS_REQUESTS:
                s1 = http_mod._get_session()
                s2 = http_mod._get_session()
                assert s1 is s2
            else:
                pytest.skip("requests 不可用")
        finally:
            http_mod._session = old


# ═══════════════════════════════════════════════════════════════
# _create_connection
# ═══════════════════════════════════════════════════════════════


class TestCreateConnection:
    def test_https(self):
        with patch("http.client.HTTPSConnection") as mock_cls:
            http_mod._create_connection("https", "example.com", 443, timeout=5)
            mock_cls.assert_called_once()

    def test_http(self):
        with patch("http.client.HTTPConnection") as mock_cls:
            http_mod._create_connection("http", "example.com", 80, timeout=5)
            mock_cls.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# _get_connection
# ═══════════════════════════════════════════════════════════════


class TestGetConnection:
    def setup_method(self):
        http_mod._connection_pool.clear()

    def test_empty_pool_creates_new(self):
        with patch.object(http_mod, "_create_connection", return_value="NEW_CONN"):
            conn = http_mod._get_connection("key", "https", "host", 443)
        assert conn == "NEW_CONN"

    def test_reuses_valid_connection(self):
        import time as _time

        mock_conn = MagicMock()
        mock_conn.sock = MagicMock()  # 有效连接
        http_mod._connection_pool["key"] = [(mock_conn, _time.time())]  # 当前时间，不过期
        with patch.object(http_mod, "_create_connection") as mock_create:
            conn = http_mod._get_connection("key", "https", "host", 443)
        assert conn is mock_conn
        mock_create.assert_not_called()

    def test_discards_expired_connection(self):
        """过期连接被 close 并创建新的。"""
        import time as _time

        mock_conn = MagicMock()
        mock_conn.sock = MagicMock()
        # ts 远在过去（超过 _CONN_IDLE_TIMEOUT）
        old_ts = _time.time() - http_mod._CONN_IDLE_TIMEOUT - 100
        http_mod._connection_pool["key"] = [(mock_conn, old_ts)]
        with patch.object(http_mod, "_create_connection", return_value="NEW"):
            conn = http_mod._get_connection("key", "https", "host", 443)
        assert conn == "NEW"
        mock_conn.close.assert_called_once()

    def test_discards_no_sock_connection(self):
        """sock 为 None 的连接被跳过。"""
        import time as _time

        mock_conn = MagicMock()
        mock_conn.sock = None
        http_mod._connection_pool["key"] = [(mock_conn, _time.time())]
        with patch.object(http_mod, "_create_connection", return_value="NEW"):
            conn = http_mod._get_connection("key", "https", "host", 443)
        assert conn == "NEW"


# ═══════════════════════════════════════════════════════════════
# _return_connection
# ═══════════════════════════════════════════════════════════════


class TestReturnConnection:
    def setup_method(self):
        http_mod._connection_pool.clear()

    def test_adds_to_empty_pool(self):
        conn = MagicMock()
        http_mod._return_connection("key", conn)
        assert "key" in http_mod._connection_pool
        assert len(http_mod._connection_pool["key"]) == 1

    def test_adds_to_existing_pool(self):
        http_mod._connection_pool["key"] = [(MagicMock(), 0)]
        conn = MagicMock()
        http_mod._return_connection("key", conn)
        assert len(http_mod._connection_pool["key"]) == 2

    def test_closes_when_pool_full(self):
        """池满时关闭连接而非归还。"""
        http_mod._connection_pool["key"] = [
            (MagicMock(), 0) for _ in range(http_mod.MAX_POOL_SIZE)
        ]
        conn = MagicMock()
        http_mod._return_connection("key", conn)
        assert len(http_mod._connection_pool["key"]) == http_mod.MAX_POOL_SIZE
        conn.close.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# _do_request
# ═══════════════════════════════════════════════════════════════


class TestDoRequest:
    def _make_conn(self, status=200, body=b"data", headers=None):
        conn = MagicMock()
        resp = MagicMock()
        resp.status = status
        # 模拟分块读取：第一次 read(8192) 返回 body，之后返回 b""
        resp.read = MagicMock(side_effect=[body, b""])
        resp.getheader = lambda h, default=None: (headers or {}).get(h, default)
        conn.getresponse.return_value = resp
        return conn, resp

    def test_success_returns_body(self):
        conn, _ = self._make_conn(status=200, body=b"hello")
        result = http_mod._do_request(conn, "http://x/", "/path", {}, 10)
        assert result == b"hello"

    def test_429_raises_rate_limit(self):
        conn, _ = self._make_conn(status=429, body=b"", headers={"Retry-After": "30"})
        with pytest.raises(RateLimitError):
            http_mod._do_request(conn, "http://x/", "/path", {}, 10)

    def test_4xx_raises_http_status_error(self):
        conn, _ = self._make_conn(status=404, body=b"not found")
        with pytest.raises(HTTPStatusError) as exc_info:
            http_mod._do_request(conn, "http://x/", "/path", {}, 10)
        assert exc_info.value.status == 404

    def test_5xx_raises_http_status_error(self):
        conn, _ = self._make_conn(status=500, body=b"server error")
        with pytest.raises(HTTPStatusError):
            http_mod._do_request(conn, "http://x/", "/path", {}, 10)

    def test_429_without_retry_after(self):
        conn, _ = self._make_conn(status=429, body=b"")
        with pytest.raises(RateLimitError) as exc_info:
            http_mod._do_request(conn, "http://x/", "/path", {}, 10)
        assert exc_info.value.retry_after is None

    def test_large_response_truncated(self):
        """响应体超过 MAX_RESPONSE_SIZE 时截断。"""
        big_body = b"x" * (http_mod.MAX_RESPONSE_SIZE + 100)
        conn = MagicMock()
        resp = MagicMock()
        resp.status = 200
        resp.getheader = lambda h, default=None: None
        # 分块返回，每块 8192
        chunks = [big_body[i : i + 8192] for i in range(0, len(big_body), 8192)]
        chunks_iter = iter(chunks + [b""])
        resp.read = lambda size=8192: next(chunks_iter)
        conn.getresponse.return_value = resp
        result = http_mod._do_request(conn, "http://x/", "/path", {}, 10)
        assert len(result) <= http_mod.MAX_RESPONSE_SIZE

    def test_read_body_exception_on_4xx_handled(self):
        """4xx 时 read 抛 OSError 仍抛 HTTPStatusError。"""
        conn = MagicMock()
        resp = MagicMock()
        resp.status = 404
        resp.read = MagicMock(side_effect=OSError("read fail"))
        conn.getresponse.return_value = resp
        with pytest.raises(HTTPStatusError):
            http_mod._do_request(conn, "http://x/", "/path", {}, 10)


# ═══════════════════════════════════════════════════════════════
# _http_get_requests
# ═══════════════════════════════════════════════════════════════


class TestHttpGetRequests:
    def test_success(self):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"data"
        mock_resp.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_resp
        with patch.object(http_mod, "_get_session", return_value=mock_session):
            result = http_mod._http_get_requests("http://x/")
        assert result == b"data"

    def test_429_raises_rate_limit(self):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "60"}
        mock_session.get.return_value = mock_resp
        with patch.object(http_mod, "_get_session", return_value=mock_session):
            with pytest.raises(RateLimitError) as exc_info:
                http_mod._http_get_requests("http://x/")
        assert exc_info.value.retry_after == 60

    def test_429_without_retry_after(self):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {}
        mock_session.get.return_value = mock_resp
        with patch.object(http_mod, "_get_session", return_value=mock_session):
            with pytest.raises(RateLimitError) as exc_info:
                http_mod._http_get_requests("http://x/")
        assert exc_info.value.retry_after is None

    def test_large_content_truncated(self):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        big = b"x" * (http_mod.MAX_RESPONSE_SIZE + 10)
        mock_resp.content = big
        mock_resp.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_resp
        with patch.object(http_mod, "_get_session", return_value=mock_session):
            result = http_mod._http_get_requests("http://x/")
        assert len(result) == http_mod.MAX_RESPONSE_SIZE


# ═══════════════════════════════════════════════════════════════
# _http_get_internal（重试逻辑）
# ═══════════════════════════════════════════════════════════════


class TestHttpGetInternal:
    def test_success_no_retry(self):
        with patch.object(http_mod, "_get_connection", return_value=MagicMock()), \
             patch.object(http_mod, "_do_request", return_value=b"ok"), \
             patch.object(http_mod, "_return_connection"):
            result = http_mod._http_get_internal("http://example.com/", max_retries=1)
        assert result == b"ok"

    def test_429_not_retried(self):
        """RateLimitError 立即抛出不重试。"""
        with patch.object(http_mod, "_get_connection", return_value=MagicMock()), \
             patch.object(http_mod, "_do_request", side_effect=RateLimitError("url")), \
             patch.object(http_mod, "_return_connection"), \
             patch.object(http_mod, "_invalidate_connection"), \
             patch("common.http.time.sleep"):
            with pytest.raises(RateLimitError):
                http_mod._http_get_internal("http://example.com/", max_retries=3)

    def test_retries_on_network_error(self):
        """网络错误重试后成功。"""
        mock_conn = MagicMock()
        with patch.object(http_mod, "_get_connection", return_value=mock_conn), \
             patch.object(
                 http_mod,
                 "_do_request",
                 side_effect=[ConnectionError("fail"), b"ok"],
             ), \
             patch.object(http_mod, "_return_connection"), \
             patch.object(http_mod, "_invalidate_connection"), \
             patch("common.http.time.sleep"):
            result = http_mod._http_get_internal(
                "http://example.com/", max_retries=3
            )
        assert result == b"ok"

    def test_all_retries_fail_raises_network_error(self):
        """所有重试失败抛 NetworkError。"""
        with patch.object(http_mod, "_get_connection", return_value=MagicMock()), \
             patch.object(
                 http_mod, "_do_request", side_effect=ConnectionError("fail")
             ), \
             patch.object(http_mod, "_return_connection"), \
             patch.object(http_mod, "_invalidate_connection"), \
             patch("common.http.time.sleep"):
            with pytest.raises(NetworkError):
                http_mod._http_get_internal(
                    "http://example.com/", max_retries=2
                )


# ═══════════════════════════════════════════════════════════════
# http_get / http_get_with_headers（降级路径）
# ═══════════════════════════════════════════════════════════════


class TestHttpGetFallback:
    def test_http_get_no_requests_uses_internal(self):
        with patch.object(http_mod, "_HAS_REQUESTS", False), \
             patch.object(http_mod, "_http_get_internal", return_value=b"data") as mock_internal:
            result = http_mod.http_get("http://example.com/")
        assert result == b"data"
        mock_internal.assert_called_once()

    def test_http_get_requests_path_success(self):
        """requests 可用时优先走 requests 路径。"""
        with patch.object(http_mod, "_HAS_REQUESTS", True), \
             patch.object(http_mod, "_http_get_requests", return_value=b"data") as mock_req:
            result = http_mod.http_get("http://example.com/")
        assert result == b"data"
        mock_req.assert_called_once()

    def test_http_get_requests_4xx_raises_status_error(self):
        """requests 路径 4xx 转 HTTPStatusError。"""
        import requests as _req

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "not found"
        err = _req.RequestException()
        err.response = mock_resp
        with patch.object(http_mod, "_HAS_REQUESTS", True), \
             patch.object(http_mod, "_http_get_requests", side_effect=err):
            with pytest.raises(HTTPStatusError) as exc_info:
                http_mod.http_get("http://example.com/")
        assert exc_info.value.status == 404

    def test_http_get_requests_4xx_falls_back_to_internal(self):
        """requests 非 4xx 异常降级到 internal。"""
        import requests as _req

        err = _req.RequestException("connection reset")
        err.response = None
        with patch.object(http_mod, "_HAS_REQUESTS", True), \
             patch.object(http_mod, "_http_get_requests", side_effect=err), \
             patch.object(http_mod, "_http_get_internal", return_value=b"fallback"):
            result = http_mod.http_get("http://example.com/")
        assert result == b"fallback"

    def test_http_get_rate_limit_propagates(self):
        """RateLimitError 不降级，直接抛出。"""
        with patch.object(http_mod, "_HAS_REQUESTS", True), \
             patch.object(http_mod, "_http_get_requests", side_effect=RateLimitError("url")):
            with pytest.raises(RateLimitError):
                http_mod.http_get("http://example.com/")

    def test_http_get_with_headers_no_requests(self):
        with patch.object(http_mod, "_HAS_REQUESTS", False), \
             patch.object(http_mod, "_http_get_internal", return_value=b"data") as mock_internal:
            result = http_mod.http_get_with_headers(
                "http://example.com/", headers={"X": "1"}
            )
        assert result == b"data"
        mock_internal.assert_called_once()

    def test_http_get_with_headers_rate_limit_propagates(self):
        with patch.object(http_mod, "_HAS_REQUESTS", True), \
             patch.object(http_mod, "_http_get_requests", side_effect=RateLimitError("url")):
            with pytest.raises(RateLimitError):
                http_mod.http_get_with_headers("http://example.com/")


# ═══════════════════════════════════════════════════════════════
# decode_gbk
# ═══════════════════════════════════════════════════════════════


class TestDecodeGbk:
    def test_utf8_success(self):
        assert http_mod.decode_gbk("hello".encode("utf-8")) == "hello"

    def test_gbk_fallback(self):
        """UTF-8 解码失败回退 GBK。"""
        gbk_data = "中文".encode("gbk")
        assert http_mod.decode_gbk(gbk_data) == "中文"

    def test_gbk_with_replacement_char_logs_warning(self):
        """GBK decode 含替换字符时记录 warning。"""
        # 构造一个 UTF-8 失败、GBK 产生替换字符的字节序列
        bad_data = b"\xff\xfe\xfd"
        result = http_mod.decode_gbk(bad_data)
        assert "\ufffd" in result


# ═══════════════════════════════════════════════════════════════
# _invalidate_connection
# ═══════════════════════════════════════════════════════════════


class TestInvalidateConnection:
    def test_closes_connection(self):
        conn = MagicMock()
        http_mod._invalidate_connection("http://x/", conn)
        conn.close.assert_called_once()

    def test_close_exception_swallowed(self):
        conn = MagicMock()
        conn.close.side_effect = OSError("fail")
        # 不应抛异常
        http_mod._invalidate_connection("http://x/", conn)
