"""portfolio/web/app.py 路由处理函数测试。

直接实例化 Handler（mock 底层 socket），测试 _check_origin / _check_auth /
_check_rate_limit / _status_from_error / do_GET / do_POST 等方法，
避免启动真实 HTTP 服务器。PortfolioManager 等均 mock。
"""

import io
import json
import sys
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from portfolio.web import app as app_mod
from portfolio.web import utils as utils_mod


# ═══════════════════════════════════════════════════════════════
# Fixtures：构造一个可调用的 Handler 实例（绕过真实 socket）
# ═══════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _isolate_token(tmp_path, monkeypatch):
    """token 存储隔离到 tmp_path。"""
    token_dir = tmp_path / "token"
    token_dir.mkdir()
    token_file = token_dir / "portfolio_web.token"
    monkeypatch.setattr(utils_mod, "_TOKEN_FILE", token_file)
    monkeypatch.setattr(utils_mod, "_TOKEN_DIR", token_dir)
    monkeypatch.setattr(utils_mod, "_token", None)
    yield


def _make_handler(
    method: str = "GET",
    path: str = "/api/health",
    headers=None,
    body: bytes = b"",
    client_ip: str = "127.0.0.1",
):
    """构造一个 Handler 实例，mock 掉 socket I/O。

    直接调用 __init__ 会触发 socket 读取，所以用 __new__ + 手动设置属性。
    """
    h = app_mod.Handler.__new__(app_mod.Handler)
    h.command = method
    h.path = path
    h.client_address = (client_ip, 12345)
    h.headers = MagicMock()
    # headers.get 行为：传入的 headers dict 优先
    hdrs = headers or {}
    h.headers.get = lambda key, default="": hdrs.get(key, default)
    # rfile / wfile
    h.rfile = io.BytesIO(body)
    h.wfile = io.BytesIO()
    # 记录响应
    h._sent_status = []
    h._sent_headers = []
    h._sent_body = []

    def fake_send_response(status):
        h._sent_status.append(status)

    def fake_send_header(k, v):
        h._sent_headers.append((k, v))

    def fake_end_headers():
        pass

    h.send_response = fake_send_response
    h.send_header = fake_send_header
    h.end_headers = fake_end_headers
    h.address_string = lambda: client_ip
    return h


# ═══════════════════════════════════════════════════════════════
# _check_origin
# ═══════════════════════════════════════════════════════════════


class TestCheckOrigin:
    def test_empty_origin_public_endpoint(self):
        h = _make_handler(path="/api/health", headers={"Origin": ""})
        assert h._check_origin() is True

    def test_empty_origin_non_public_with_valid_token(self):
        token = utils_mod._ensure_token()
        h = _make_handler(
            path="/api/positions",
            headers={"Origin": "", "Authorization": f"Bearer {token}"},
        )
        assert h._check_origin() is True

    def test_empty_origin_non_public_no_token_rejected(self):
        h = _make_handler(path="/api/positions", headers={"Origin": ""})
        assert h._check_origin() is False

    def test_allowed_origin(self):
        h = _make_handler(
            path="/api/positions",
            headers={"Origin": "http://127.0.0.1:8765"},
        )
        assert h._check_origin() is True

    def test_disallowed_origin_rejected(self):
        h = _make_handler(
            path="/api/positions",
            headers={"Origin": "http://evil.com:8765"},
        )
        assert h._check_origin() is False

    def test_url_token_for_index_page(self):
        """页面导航支持 ?token=<token>。"""
        token = utils_mod._ensure_token()
        h = _make_handler(
            path=f"/?token={token}",
            headers={"Origin": ""},
        )
        assert h._check_origin() is True

    def test_invalid_url_token_rejected(self):
        h = _make_handler(path="/?token=wrong", headers={"Origin": ""})
        assert h._check_origin() is False


# ═══════════════════════════════════════════════════════════════
# _check_auth
# ═══════════════════════════════════════════════════════════════


class TestCheckAuth:
    def test_valid_bearer_token(self):
        token = utils_mod._ensure_token()
        h = _make_handler(headers={"Authorization": f"Bearer {token}"})
        assert h._check_auth() is True

    def test_invalid_bearer_token(self):
        h = _make_handler(headers={"Authorization": "Bearer wrong"})
        assert h._check_auth() is False

    def test_no_auth(self):
        h = _make_handler(headers={})
        assert h._check_auth() is False

    def test_url_token_for_index(self):
        token = utils_mod._ensure_token()
        h = _make_handler(path=f"/?token={token}")
        assert h._check_auth() is True


# ═══════════════════════════════════════════════════════════════
# _check_rate_limit
# ═══════════════════════════════════════════════════════════════


class TestCheckRateLimit:
    def test_under_limit_passes(self):
        app_mod.Handler.reset_rate_limit_for_tests()
        h = _make_handler()
        assert h._check_rate_limit() is True

    def test_over_limit_blocked(self, monkeypatch):
        """超过限流阈值返回 False。"""
        monkeypatch.setattr(app_mod, "_RATE_LIMIT_REQUESTS", 2)
        app_mod.Handler.reset_rate_limit_for_tests()
        h1 = _make_handler()
        h2 = _make_handler()
        assert h1._check_rate_limit() is True
        assert h2._check_rate_limit() is True
        h3 = _make_handler()
        assert h3._check_rate_limit() is False
        app_mod.Handler.reset_rate_limit_for_tests()


# ═══════════════════════════════════════════════════════════════
# _status_from_error
# ═══════════════════════════════════════════════════════════════


class TestStatusFromError:
    def test_valid_code(self):
        h = _make_handler()
        assert h._status_from_error({"code": 404}) == HTTPStatus.NOT_FOUND

    def test_invalid_code_falls_back_400(self):
        h = _make_handler()
        assert h._status_from_error({"code": 999}) == HTTPStatus.BAD_REQUEST

    def test_missing_code_defaults_400(self):
        h = _make_handler()
        assert h._status_from_error({}) == HTTPStatus.BAD_REQUEST


# ═══════════════════════════════════════════════════════════════
# do_GET 路由
# ═══════════════════════════════════════════════════════════════


class TestDoGetRoutes:
    def test_health(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        h = _make_handler(
            path="/api/health", headers={"Authorization": f"Bearer {token}"}
        )
        with (
            patch.object(app_mod, "_get_pm") as mock_pm,
            patch.object(app_mod, "_monitor_enabled", True),
            patch.object(app_mod, "_monitor_interval", 300),
            patch.object(app_mod, "_monitor_last_result", {"alerts": 0}),
        ):
            mock_pm.return_value.is_example = False
            mock_pm.return_value.summary = MagicMock()
            h.do_GET()
        assert h._sent_status[-1] == HTTPStatus.OK

    def test_favicon(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        h = _make_handler(
            path="/favicon.ico", headers={"Authorization": f"Bearer {token}"}
        )
        h.do_GET()
        assert h._sent_status[-1] == HTTPStatus.NO_CONTENT

    def test_unknown_path_returns_404(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        h = _make_handler(
            path="/api/unknown", headers={"Authorization": f"Bearer {token}"}
        )
        h.do_GET()
        assert h._sent_status[-1] == HTTPStatus.NOT_FOUND

    def test_index_page(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        h = _make_handler(path="/", headers={"Authorization": f"Bearer {token}"})
        with patch.object(app_mod, "_collect_code_name_map", return_value=[]):
            h.do_GET()
        assert h._sent_status[-1] == HTTPStatus.OK

    def test_monitor_endpoint(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        h = _make_handler(
            path="/api/monitor", headers={"Authorization": f"Bearer {token}"}
        )
        with (
            patch.object(app_mod, "_monitor_enabled", True),
            patch.object(app_mod, "_monitor_interval", 300),
            patch.object(app_mod, "_monitor_last_result", {"alerts": 1}),
        ):
            h.do_GET()
        assert h._sent_status[-1] == HTTPStatus.OK

    def test_get_one_position(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        h = _make_handler(
            path="/api/positions/sh600519",
            headers={"Authorization": f"Bearer {token}"},
        )
        with patch.object(app_mod, "_get_pm") as mock_pm:
            mock_pm.return_value.get_position.return_value = {"code": "sh600519"}
            mock_pm.return_value.get_watch.return_value = None
            h.do_GET()
        assert h._sent_status[-1] == HTTPStatus.OK

    def test_get_one_not_found(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        h = _make_handler(
            path="/api/positions/sh999999",
            headers={"Authorization": f"Bearer {token}"},
        )
        with patch.object(app_mod, "_get_pm") as mock_pm:
            mock_pm.return_value.get_position.return_value = None
            mock_pm.return_value.get_watch.return_value = None
            h.do_GET()
        assert h._sent_status[-1] == HTTPStatus.NOT_FOUND

    def test_get_one_empty_code(self):
        """空 code 直接调 _serve_get_one 返回 404。"""
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        h = _make_handler(
            path="/api/positions/",
            headers={"Authorization": f"Bearer {token}"},
        )
        h._serve_get_one("")
        assert h._sent_status[-1] == HTTPStatus.NOT_FOUND

    def test_trades_endpoint(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        h = _make_handler(
            path="/api/trades", headers={"Authorization": f"Bearer {token}"}
        )
        with patch("portfolio.trade_log.TradeLog") as mock_tl_class:
            mock_tl = mock_tl_class.return_value
            mock_tl.query.return_value = []
            mock_tl.stats.return_value = {}
            h.do_GET()
        assert h._sent_status[-1] == HTTPStatus.OK

    def test_trades_endpoint_exception_returns_empty(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        h = _make_handler(
            path="/api/trades", headers={"Authorization": f"Bearer {token}"}
        )
        with patch("portfolio.trade_log.TradeLog", side_effect=RuntimeError("boom")):
            h.do_GET()
        assert h._sent_status[-1] == HTTPStatus.OK

    def test_positions_list_with_quotes(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        h = _make_handler(
            path="/api/positions", headers={"Authorization": f"Bearer {token}"}
        )
        mock_pm = MagicMock()
        mock_pm.to_dict.return_value = {
            "positions": [{"code": "sh600519", "cost": 100, "quantity": 10}],
            "watchlist": [{"code": "sh600000", "target_buy": 90}],
        }
        mock_pm.summary.return_value = {"total": 1}
        mock_quote = MagicMock()
        mock_quote.code = "sh600519"
        mock_quote.price = 110.0
        mock_quote.change_pct = 5.0
        mock_quote2 = MagicMock()
        mock_quote2.code = "sh600000"
        mock_quote2.price = 10.0
        mock_quote2.change_pct = 2.0
        with (
            patch.object(app_mod, "_get_pm", return_value=mock_pm),
            patch.object(utils_mod, "_virtual_mode", False),
            patch("data.get_quotes", return_value=[mock_quote, mock_quote2]),
        ):
            h.do_GET()
        assert h._sent_status[-1] == HTTPStatus.OK


# ═══════════════════════════════════════════════════════════════
# do_POST 路由
# ═══════════════════════════════════════════════════════════════


class TestDoPostRoutes:
    def test_post_non_positions_path_404(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        h = _make_handler(
            method="POST",
            path="/api/other",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        h.do_POST()
        assert h._sent_status[-1] == HTTPStatus.NOT_FOUND

    def test_post_wrong_content_type_415(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        h = _make_handler(
            method="POST",
            path="/api/positions",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "text/plain"},
        )
        h.do_POST()
        assert h._sent_status[-1] == HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    def test_post_invalid_json_400(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        h = _make_handler(
            method="POST",
            path="/api/positions",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            body=b"not json{",
        )
        h.do_POST()
        assert h._sent_status[-1] == HTTPStatus.BAD_REQUEST

    def test_post_valid_action_returns_ok(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        body = json.dumps(
            {"action": "add_position", "code": "sh600519", "cost": 100, "quantity": 10}
        ).encode()
        h = _make_handler(
            method="POST",
            path="/api/positions",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            body=body,
        )
        mock_pm = MagicMock()
        with (
            patch.object(app_mod, "_get_pm", return_value=mock_pm),
            patch(
                "portfolio.web.app.dispatch", return_value={"ok": True, "data": {}}
            ) as mock_dispatch,
        ):
            h.do_POST()
        assert h._sent_status[-1] == HTTPStatus.OK
        mock_dispatch.assert_called_once()

    def test_post_action_error_returns_error_status(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        body = json.dumps({"action": "add_position", "code": "sh600519"}).encode()
        h = _make_handler(
            method="POST",
            path="/api/positions",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            body=body,
        )
        mock_pm = MagicMock()
        with (
            patch.object(app_mod, "_get_pm", return_value=mock_pm),
            patch(
                "portfolio.web.app.dispatch",
                return_value={"ok": False, "code": 400, "error": "missing field"},
            ),
        ):
            h.do_POST()
        assert h._sent_status[-1] == HTTPStatus.BAD_REQUEST

    def test_post_dispatch_exception_500(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        body = json.dumps({"action": "add_position", "code": "sh600519"}).encode()
        h = _make_handler(
            method="POST",
            path="/api/positions",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            body=body,
        )
        with (
            patch.object(app_mod, "_get_pm", return_value=MagicMock()),
            patch("portfolio.web.app.dispatch", side_effect=RuntimeError("boom")),
        ):
            h.do_POST()
        assert h._sent_status[-1] == HTTPStatus.INTERNAL_SERVER_ERROR


# ═══════════════════════════════════════════════════════════════
# do_HEAD / do_PUT / do_DELETE / do_PATCH
# ═══════════════════════════════════════════════════════════════


class TestOtherMethods:
    def test_head_known_path(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        h = _make_handler(
            path="/api/health", headers={"Authorization": f"Bearer {token}"}
        )
        h.do_HEAD()
        assert h._sent_status[-1] == HTTPStatus.OK

    def test_head_unknown_path(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        h = _make_handler(
            path="/api/unknown", headers={"Authorization": f"Bearer {token}"}
        )
        h.do_HEAD()
        assert h._sent_status[-1] == HTTPStatus.NOT_FOUND

    def test_put_returns_405(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        h = _make_handler(
            method="PUT",
            path="/api/positions",
            headers={"Authorization": f"Bearer {token}"},
        )
        h.do_PUT()
        assert h._sent_status[-1] == HTTPStatus.METHOD_NOT_ALLOWED

    def test_delete_returns_405(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        h = _make_handler(
            method="DELETE",
            path="/api/positions",
            headers={"Authorization": f"Bearer {token}"},
        )
        h.do_DELETE()
        assert h._sent_status[-1] == HTTPStatus.METHOD_NOT_ALLOWED

    def test_patch_returns_405(self):
        token = utils_mod._ensure_token()
        app_mod.Handler.reset_rate_limit_for_tests()
        h = _make_handler(
            method="PATCH",
            path="/api/positions",
            headers={"Authorization": f"Bearer {token}"},
        )
        h.do_PATCH()
        assert h._sent_status[-1] == HTTPStatus.METHOD_NOT_ALLOWED


# ═══════════════════════════════════════════════════════════════
# make_server / VERSION
# ═══════════════════════════════════════════════════════════════


class TestMakeServer:
    def test_version_string(self):
        assert isinstance(app_mod.VERSION, str)
        assert len(app_mod.VERSION) > 0

    def test_make_server_creates_instance(self, tmp_path):
        data_file = tmp_path / "portfolio.json"
        data_file.write_text(
            json.dumps({"version": 2, "positions": [], "watchlist": []}),
            encoding="utf-8",
        )
        srv = app_mod.make_server("127.0.0.1", 0, str(data_file))
        try:
            assert srv is not None
            assert srv.server_address[0] == "127.0.0.1"
        finally:
            srv.server_close()

    def test_make_server_virtual_mode(self, tmp_path):
        data_file = tmp_path / "portfolio.json"
        data_file.write_text(
            json.dumps({"version": 2, "positions": [], "watchlist": []}),
            encoding="utf-8",
        )
        srv = app_mod.make_server("127.0.0.1", 0, str(data_file), virtual=True)
        try:
            assert srv is not None
        finally:
            srv.server_close()
