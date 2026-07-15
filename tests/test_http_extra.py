"""common/http.py 补充测试（覆盖率提升）。"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestParseUrl:
    def test_http_url(self):
        from common.http import _parse_url

        key, scheme, host, port, path = _parse_url("http://example.com/api?x=1")
        assert scheme == "http"
        assert host == "example.com"
        assert port == 80
        assert "/api" in path

    def test_https_url(self):
        from common.http import _parse_url

        key, scheme, host, port, path = _parse_url("https://example.com:443/path")
        assert scheme == "https"
        assert port == 443

    def test_with_port(self):
        from common.http import _parse_url

        key, scheme, host, port, path = _parse_url("http://localhost:8080/test")
        assert port == 8080

    def test_invalid_scheme_rejected(self):
        from common.http import _parse_url

        try:
            _parse_url("file:///etc/passwd")
            assert False, "Should raise"
        except ValueError:
            pass


class TestHttpGet:
    def test_returns_bytes(self):
        from common.http import http_get

        with (
            patch("common.http._HAS_REQUESTS", False),
            patch("common.http._http_get_internal", return_value=b"data"),
        ):
            result = http_get("http://example.com/test")
            assert result == b"data"

    def test_none_on_failure(self):
        from common.http import http_get

        with (
            patch("common.http._HAS_REQUESTS", False),
            patch("common.http._http_get_internal", return_value=None),
        ):
            http_get("http://example.com/test")


class TestHttpGetWithHeaders:
    def test_returns_bytes(self):
        from common.http import http_get_with_headers

        with (
            patch("common.http._HAS_REQUESTS", False),
            patch("common.http._http_get_internal", return_value=b"data"),
        ):
            result = http_get_with_headers(
                "http://example.com/test", headers={"Referer": "test"}
            )
            assert result == b"data"
