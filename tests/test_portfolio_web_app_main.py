"""portfolio/web/app.py main() 与额外分支覆盖测试。

重点覆盖 main() 入口的各分支（公网绑定拒绝、启动失败、notify/monitor 开关、
浏览器打开、serve_forever/KeyboardInterrupt/shutdown）以及 do_POST 通知分支、
_serve_list 无行情分支、_serve_get_one ValidationError 分支等。
"""

import io
import json
import sys
import threading
from http import HTTPStatus
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from portfolio.web import app as app_mod
from portfolio.web import utils as utils_mod


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    token_dir = tmp_path / "token"
    token_dir.mkdir()
    token_file = token_dir / "portfolio_web.token"
    monkeypatch.setattr(utils_mod, "_TOKEN_FILE", token_file)
    monkeypatch.setattr(utils_mod, "_TOKEN_DIR", token_dir)
    monkeypatch.setattr(utils_mod, "_token", None)
    monkeypatch.setattr(utils_mod, "_notify_enabled", False)
    monkeypatch.setattr(utils_mod, "_virtual_mode", False)
    monkeypatch.setattr(app_mod, "_monitor_enabled", False)
    utils_mod._reset_pm_for_tests()
    app_mod.Handler.reset_rate_limit_for_tests()
    yield
    utils_mod._reset_pm_for_tests()
    utils_mod._token = None


def _make_handler(method="GET", path="/api/health", headers=None, body=b"", client_ip="127.0.0.1"):
    h = app_mod.Handler.__new__(app_mod.Handler)
    h.command = method
    h.path = path
    h.client_address = (client_ip, 12345)
    h.headers = MagicMock()
    hdrs = dict(headers or {})
    # 自动补充 Content-Length（POST 读 body 依赖此头）
    if body and "Content-Length" not in hdrs:
        hdrs["Content-Length"] = str(len(body))
    h.headers.get = lambda key, default="": hdrs.get(key, default)
    h.rfile = io.BytesIO(body)
    h.wfile = io.BytesIO()
    h._sent_status = []
    h._sent_headers = []
    h._sent_body = []

    def fake_send_response(status):
        h._sent_status.append(status)

    def fake_send_header(k, v):
        h._sent_headers.append((k, v))

    h.send_response = fake_send_response
    h.send_header = fake_send_header
    h.end_headers = lambda: None
    h.address_string = lambda: client_ip
    return h


def _token():
    return utils_mod._ensure_token()


# ═══════════════════════════════════════════════════════════════
# main() 分支覆盖
# ═══════════════════════════════════════════════════════════════


class TestMainPublicBindRefused:
    def test_public_bind_without_flag_exits(self):
        with patch("sys.argv", ["prog", "--host", "0.0.0.0", "--port", "0"]):
            with pytest.raises(SystemExit) as exc:
                app_mod.main()
        assert exc.value.code == 1


class TestMainBindFailure:
    def test_make_server_oserror_exits(self):
        with patch("sys.argv", ["prog", "--host", "127.0.0.1", "--port", "0"]):
            with patch.object(app_mod, "make_server", side_effect=OSError("addr in use")):
                with pytest.raises(SystemExit) as exc:
                    app_mod.main()
        assert exc.value.code == 1


class TestMainNormalStartup:
    def _run_main(self, argv_extra, monkeypatch):
        """运行 main()，serve_forever 立即返回（模拟启动后立即停止）。"""
        fake_server = MagicMock()
        fake_server.server_address = ("127.0.0.1", 8765)
        fake_server.server_close = MagicMock()

        def _fake_make_server(host, port, data_file=None, virtual=False):
            utils_mod._virtual_mode = virtual
            return fake_server

        monkeypatch.setattr(app_mod, "make_server", _fake_make_server)
        monkeypatch.setattr(utils_mod, "_monitor_stop_event", threading.Event())
        argv = ["prog", "--host", "127.0.0.1", "--port", "0", "--no-open"] + argv_extra
        monkeypatch.setattr(sys, "argv", argv)
        # serve_forever 正常返回
        fake_server.serve_forever = MagicMock()
        app_mod.main()
        return fake_server

    def test_default_startup(self, monkeypatch):
        srv = self._run_main([], monkeypatch)
        srv.serve_forever.assert_called_once()
        srv.server_close.assert_called_once()

    def test_no_notify(self, monkeypatch, capsys):
        # --no-notify 走 else 分支（打印禁用，不设置 _notify_enabled）
        self._run_main(["--no-notify"], monkeypatch)
        out = capsys.readouterr().out
        assert "已禁用" in out

    def test_no_monitor(self, monkeypatch, capsys):
        # --no-monitor 走 else 分支（打印禁用）
        self._run_main(["--no-monitor"], monkeypatch)
        out = capsys.readouterr().out
        assert "已禁用" in out

    def test_keyboard_interrupt(self, monkeypatch):
        fake_server = MagicMock()
        fake_server.server_address = ("127.0.0.1", 8765)
        fake_server.server_close = MagicMock()
        monkeypatch.setattr(app_mod, "make_server", lambda *a, **kw: fake_server)
        monkeypatch.setattr(utils_mod, "_monitor_stop_event", threading.Event())
        monkeypatch.setattr(sys, "argv", ["prog", "--host", "127.0.0.1", "--port", "0", "--no-open"])
        fake_server.serve_forever = MagicMock(side_effect=KeyboardInterrupt())
        # 不应抛异常
        app_mod.main()
        fake_server.server_close.assert_called_once()

    def test_with_notify_no_channels(self, monkeypatch):
        self._run_main(["--notify"], monkeypatch)
        assert utils_mod._notify_enabled is True

    def test_virtual_mode(self, monkeypatch):
        self._run_main(["--virtual"], monkeypatch)
        assert utils_mod._virtual_mode is True

    def test_monitor_with_interval(self, monkeypatch):
        fake_server = MagicMock()
        fake_server.server_address = ("127.0.0.1", 8765)
        monkeypatch.setattr(app_mod, "make_server", lambda *a, **kw: fake_server)
        monkeypatch.setattr(utils_mod, "_monitor_stop_event", threading.Event())
        monkeypatch.setattr(sys, "argv", ["prog", "--host", "127.0.0.1", "--port", "0", "--no-open", "--monitor-interval", "10"])
        fake_server.serve_forever = MagicMock()
        app_mod.main()
        assert app_mod._monitor_enabled is True
        # 停掉监控线程
        utils_mod._monitor_stop_event.set()


class TestMainBrowserOpen:
    def test_browser_open_success(self, monkeypatch):
        fake_server = MagicMock()
        fake_server.server_address = ("127.0.0.1", 8765)
        monkeypatch.setattr(app_mod, "make_server", lambda *a, **kw: fake_server)
        monkeypatch.setattr(utils_mod, "_monitor_stop_event", threading.Event())
        monkeypatch.setattr(sys, "argv", ["prog", "--host", "127.0.0.1", "--port", "0"])
        fake_server.serve_forever = MagicMock()
        with patch("webbrowser.open") as m:
            app_mod.main()
        m.assert_called_once()

    def test_browser_open_failure(self, monkeypatch):
        fake_server = MagicMock()
        fake_server.server_address = ("127.0.0.1", 8765)
        monkeypatch.setattr(app_mod, "make_server", lambda *a, **kw: fake_server)
        monkeypatch.setattr(utils_mod, "_monitor_stop_event", threading.Event())
        monkeypatch.setattr(sys, "argv", ["prog", "--host", "127.0.0.1", "--port", "0"])
        fake_server.serve_forever = MagicMock()
        with patch("webbrowser.open", side_effect=Exception("no browser")):
            app_mod.main()  # 不应抛异常


class TestMainPublicBind:
    def test_public_bind_with_flag(self, monkeypatch):
        fake_server = MagicMock()
        fake_server.server_address = ("0.0.0.0", 8765)
        monkeypatch.setattr(app_mod, "make_server", lambda *a, **kw: fake_server)
        monkeypatch.setattr(utils_mod, "_monitor_stop_event", threading.Event())
        monkeypatch.setattr(sys, "argv", ["prog", "--host", "0.0.0.0", "--port", "0", "--allow-public-bind", "--no-open"])
        fake_server.serve_forever = MagicMock()
        app_mod.main()
        fake_server.serve_forever.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# do_POST 通知分支
# ═══════════════════════════════════════════════════════════════


class TestPostNotify:
    def test_post_success_triggers_notify(self, tmp_path, monkeypatch):
        data_file = tmp_path / "portfolio.json"
        data_file.write_text(json.dumps({"version": 2, "positions": [], "watchlist": []}), encoding="utf-8")
        monkeypatch.setattr(utils_mod, "_data_file", str(data_file))
        monkeypatch.setattr(utils_mod, "_virtual_mode", False)
        utils_mod._reset_pm_for_tests()

        token = _token()
        body = json.dumps({"action": "add_position", "code": "sh600519", "name": "茅台", "cost": 100, "quantity": 100}).encode()
        h = _make_handler(
            method="POST", path="/api/positions",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            body=body,
        )
        with patch.object(app_mod, "_notify_async") as m_notify:
            h.do_POST()
        assert h._sent_status[-1] == HTTPStatus.OK
        m_notify.assert_called_once()
        # 清理测试数据
        utils_mod._reset_pm_for_tests()

    def test_post_error_no_notify(self, tmp_path, monkeypatch):
        data_file = tmp_path / "portfolio.json"
        data_file.write_text(json.dumps({"version": 2, "positions": [], "watchlist": []}), encoding="utf-8")
        monkeypatch.setattr(utils_mod, "_data_file", str(data_file))
        monkeypatch.setattr(utils_mod, "_virtual_mode", False)
        utils_mod._reset_pm_for_tests()

        token = _token()
        # 无效 action -> dispatch 返回 error
        body = json.dumps({"action": "unknown_action", "code": "sh600519"}).encode()
        h = _make_handler(
            method="POST", path="/api/positions",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            body=body,
        )
        with patch.object(app_mod, "_notify_async") as m_notify:
            h.do_POST()
        m_notify.assert_not_called()
        utils_mod._reset_pm_for_tests()


# ═══════════════════════════════════════════════════════════════
# _serve_list 无行情分支 + 自选行情分支
# ═══════════════════════════════════════════════════════════════


class TestServeListNoQuotes:
    def test_list_no_quote_data(self, tmp_path, monkeypatch):
        data_file = tmp_path / "portfolio.json"
        data_file.write_text(json.dumps({
            "version": 2,
            "positions": [{"code": "sh600519", "name": "茅台", "cost": 100, "quantity": 100, "tags": []}],
            "watchlist": [{"code": "sz000858", "name": "五粮液", "target_buy": 70, "target_sell": 90}],
        }), encoding="utf-8")
        monkeypatch.setattr(utils_mod, "_data_file", str(data_file))
        monkeypatch.setattr(utils_mod, "_virtual_mode", False)
        utils_mod._reset_pm_for_tests()

        token = _token()
        h = _make_handler(path="/api/positions", headers={"Authorization": f"Bearer {token}"})
        with patch("data.get_quotes", side_effect=Exception("net err")):
            h.do_GET()
        assert h._sent_status[-1] == HTTPStatus.OK
        utils_mod._reset_pm_for_tests()


# ═══════════════════════════════════════════════════════════════
# _serve_get_one ValidationError 分支
# ═══════════════════════════════════════════════════════════════


class TestServeGetOneValidation:
    def test_validation_error_returns_404(self, tmp_path, monkeypatch):
        data_file = tmp_path / "portfolio.json"
        data_file.write_text(json.dumps({"version": 2, "positions": [], "watchlist": []}), encoding="utf-8")
        monkeypatch.setattr(utils_mod, "_data_file", str(data_file))
        monkeypatch.setattr(utils_mod, "_virtual_mode", False)
        utils_mod._reset_pm_for_tests()

        token = _token()
        h = _make_handler(path="/api/positions/!!!", headers={"Authorization": f"Bearer {token}"})
        from common.exceptions import ValidationError
        with patch("portfolio.manager.PortfolioManager.get_position", side_effect=ValidationError("code", "!!!", "invalid format")):
            h.do_GET()
        assert h._sent_status[-1] == HTTPStatus.NOT_FOUND
        utils_mod._reset_pm_for_tests()


# ═══════════════════════════════════════════════════════════════
# do_GET 异常分支
# ═══════════════════════════════════════════════════════════════


class TestDoGetException:
    def test_serve_list_exception_500(self, tmp_path, monkeypatch):
        data_file = tmp_path / "portfolio.json"
        data_file.write_text(json.dumps({"version": 2, "positions": [], "watchlist": []}), encoding="utf-8")
        monkeypatch.setattr(utils_mod, "_data_file", str(data_file))
        utils_mod._reset_pm_for_tests()

        token = _token()
        h = _make_handler(path="/api/positions", headers={"Authorization": f"Bearer {token}"})
        with patch("portfolio.web.app._get_pm", side_effect=RuntimeError("boom")):
            h.do_GET()
        assert h._sent_status[-1] == HTTPStatus.INTERNAL_SERVER_ERROR
        utils_mod._reset_pm_for_tests()


# ═══════════════════════════════════════════════════════════════
# _read_body / _check_rate_limit 边界
# ═══════════════════════════════════════════════════════════════


class TestReadBody:
    def test_no_content_length(self):
        h = _make_handler(headers={})
        assert h._read_body() == b""

    def test_body_too_large(self):
        h = _make_handler(headers={"Content-Length": str(app_mod.MAX_BODY_BYTES + 1)})
        with pytest.raises(ValueError, match="body too large"):
            h._read_body()

    def test_normal_body(self):
        h = _make_handler(headers={"Content-Length": "5"}, body=b"hello")
        assert h._read_body() == b"hello"


class TestRateLimitEdge:
    def test_no_client_address(self):
        h = _make_handler()
        h.client_address = None
        # 不应抛异常
        assert isinstance(h._check_rate_limit(), bool)
