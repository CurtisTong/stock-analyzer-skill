"""portfolio-web Origin 白名单按实际端口重建的回归测试。

不变量：
- 自定义端口（--port 9000）下，页面同源 Origin 必须放行（鉴权仍强制），
  不得因硬编码 8765 白名单而全部 403；
- 非白名单 Origin 仍拒绝（防 CSRF 屏障保留）；
- 公网绑定（host 0.0.0.0）时 Origin 退位给 Bearer 鉴权。

回归背景（2026-11-02 skill 审查 P1）：_ALLOWED_ORIGINS 硬编码 8765，
浏览器同源 POST 带 Origin: http://127.0.0.1:<port>，--port != 8765 时
页面能打开但一切写操作 403 forbidden_origin；CI smoke_test 只测 8765
故不可见。
"""

from __future__ import annotations

import threading
import urllib.error
import urllib.request
from pathlib import Path

import portfolio.web.app as app
import portfolio.web.utils as web_utils


def _setup_token_dir(tmp_path: Path, monkeypatch) -> None:
    """token 落盘重定向到 tmp，避免测试触碰 ~/.config。"""
    monkeypatch.setattr(web_utils, "_TOKEN_DIR", tmp_path)
    monkeypatch.setattr(web_utils, "_TOKEN_FILE", tmp_path / "portfolio_web.token")
    monkeypatch.setattr(web_utils, "_token", None)


def _start_server(tmp_path, monkeypatch, host: str = "127.0.0.1"):
    """在临时端口启动服务（不 serve），返回 (server, port)。"""
    _setup_token_dir(tmp_path, monkeypatch)
    data_file = tmp_path / "portfolio.json"
    data_file.write_text('{"version":2,"positions":[],"watchlist":[]}', encoding="utf-8")
    server = app.make_server(host, 0, data_file=str(data_file))
    port = server.server_address[1]
    # port=0 时内核分配真实端口，需按真实端口重建白名单（CLI 显式端口无此问题）
    app._rebuild_allowed_origins(host, port)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, port


def _post(port: int, origin: str | None) -> urllib.error.HTTPError | None:
    """POST /api/positions，返回非 2xx 的 HTTPError（无异常则 None）。"""
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/positions",
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    if origin is not None:
        req.add_header("Origin", origin)
    try:
        urllib.request.urlopen(req, timeout=10)
        return None
    except urllib.error.HTTPError as e:
        return e


class TestRebuildAllowedOrigins:
    def test_custom_port_rebuilds_whitelist(self, tmp_path, monkeypatch):
        app._rebuild_allowed_origins("127.0.0.1", 9000)
        assert "http://127.0.0.1:9000" in app._ALLOWED_ORIGINS
        assert "http://localhost:9000" in app._ALLOWED_ORIGINS
        assert "https://127.0.0.1:9000" in app._ALLOWED_ORIGINS
        # 旧端口不再残留
        assert not any(":8765" in o for o in app._ALLOWED_ORIGINS)

    def test_public_bind_disables_origin_barrier(self, tmp_path, monkeypatch):
        app._rebuild_allowed_origins("0.0.0.0", 9000)
        assert app._ALLOWED_ORIGINS is None

    def test_default_port_matches_original_set(self, tmp_path, monkeypatch):
        app._rebuild_allowed_origins("127.0.0.1", 8765)
        assert app._ALLOWED_ORIGINS == frozenset(
            (
                "http://127.0.0.1:8765",
                "http://localhost:8765",
                "https://127.0.0.1:8765",
                "https://localhost:8765",
            )
        )


class TestOriginEndToEnd:
    def test_same_origin_custom_port_not_403(self, tmp_path, monkeypatch):
        """自定义端口：同源 POST 不再 403，落到鉴权层返回 401（未带 token）。"""
        server, port = _start_server(tmp_path, monkeypatch)
        try:
            err = _post(port, origin=f"http://127.0.0.1:{port}")
            assert err is not None and err.code == 401
        finally:
            server.shutdown()
            server.server_close()

    def test_foreign_origin_still_403(self, tmp_path, monkeypatch):
        """跨站 Origin 仍被拒（CSRF 屏障保留）。"""
        server, port = _start_server(tmp_path, monkeypatch)
        try:
            err = _post(port, origin="http://evil.example")
            assert err is not None and err.code == 403
            assert "forbidden_origin" in err.read().decode("utf-8")
        finally:
            server.shutdown()
            server.server_close()

    def test_default_port_regression_guard(self, tmp_path, monkeypatch):
        """默认端口行为不回归：同源放行→401，异源→403。"""
        server, port = _start_server(tmp_path, monkeypatch)
        try:
            assert _post(port, origin=f"http://127.0.0.1:{port}").code == 401
            assert _post(port, origin="http://evil.example").code == 403
        finally:
            server.shutdown()
            server.server_close()
