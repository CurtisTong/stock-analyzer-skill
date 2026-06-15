"""portfolio_web server 端到端测试：路由、action 校验、并发安全、HTML 页。"""
import json
import socket
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path

import pytest

import portfolio_web
from portfolio import PortfolioManager
from portfolio.web import utils as portfolio_web_utils


# ═══════════════════════════════════════════════════════════════
# Token 隔离：monkeypatch 到 tmp_path 避免读写真实 ~/.config
# ═══════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _isolate_token(tmp_path, monkeypatch):
    """每个测试用例独立的 token 存储路径。"""
    token_dir = tmp_path / "token"
    token_dir.mkdir()
    token_file = token_dir / "portfolio_web.token"
    # 同时 monkeypatch portfolio_web 和 portfolio.web.utils 的属性
    monkeypatch.setattr(portfolio_web, "_TOKEN_FILE", token_file)
    monkeypatch.setattr(portfolio_web, "_TOKEN_DIR", token_dir)
    monkeypatch.setattr(portfolio_web, "_token", None)
    monkeypatch.setattr(portfolio_web_utils, "_TOKEN_FILE", token_file)
    monkeypatch.setattr(portfolio_web_utils, "_TOKEN_DIR", token_dir)
    monkeypatch.setattr(portfolio_web_utils, "_token", None)
    yield


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════


def _free_port() -> int:
    """找一个空闲端口（让 OS 分配）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def running_server(tmp_path: Path):
    """启动 ThreadingHTTPServer 在空闲端口，yield (base_url, data_file, token)。

    用法::

        with running_server(tmp_path) as (url, data_file, token):
            ...
    """
    data_file = tmp_path / "portfolio.json"
    data_file.write_text(
        json.dumps({"version": 2, "positions": [], "watchlist": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    port = _free_port()
    srv = portfolio_web.make_server("127.0.0.1", port, str(data_file))
    token = portfolio_web._ensure_token()
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}", data_file, token
    finally:
        srv.shutdown()
        srv.server_close()


def _hit(url: str, method: str = "GET", body=None, content_type: str = "application/json",
         raw_body: bytes = None, token: str = None):
    """HTTP 客户端 helper，返回 (status, json_or_text)。"""
    if raw_body is not None:
        data = raw_body
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
    else:
        data = None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", content_type)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        r = urllib.request.urlopen(req, timeout=5)
        return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


# ═══════════════════════════════════════════════════════════════
# 路由
# ═══════════════════════════════════════════════════════════════


class TestRouting:
    def test_health_ok(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/health")
            assert status == 200
            j = json.loads(body)
            assert j["ok"] is True
            assert j["version"] == portfolio_web.VERSION
            assert "uptime_sec" in j
            assert j["example"] is False

    def test_health_no_auth_required(self, tmp_path):
        """health 端点免认证。"""
        with running_server(tmp_path) as (base, _, _):
            status, body = _hit(f"{base}/api/health")
            assert status == 200

    def test_health_example_flag(self, tmp_path):
        # 不写 portfolio.json，应回退到 example
        with running_server(tmp_path) as (base, _, _):
            # 此时 manager 加载了空文件，重启 server 让它重新加载
            pass
        # 直接构造：data_file 指向不存在路径
        data_file = tmp_path / "nope.json"
        port = _free_port()
        srv = portfolio_web.make_server("127.0.0.1", port, str(data_file))
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            status, body = _hit(f"http://127.0.0.1:{port}/api/health")
            assert status == 200
            j = json.loads(body)
            assert j["example"] is True
        finally:
            srv.shutdown()
            srv.server_close()

    def test_list_positions_empty(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", token=token)
            assert status == 200
            j = json.loads(body)
            assert j["ok"]
            assert j["data"]["positions"] == []
            assert j["data"]["watchlist"] == []
            assert "持仓" in j["data"]["summary"]

    def test_list_positions_populated(self, tmp_path):
        data_file = tmp_path / "portfolio.json"
        data_file.write_text(json.dumps({
            "version": 2,
            "positions": [{"code": "sh600989", "name": "宝丰", "cost": 18.5,
                           "quantity": 1000, "buy_date": "2025-03-15", "tags": ["长线"]}],
            "watchlist": [{"code": "sz000807", "name": "云铝", "target_buy": 12.0,
                           "target_sell": 18.0, "added_date": "2025-06-01"}],
        }, ensure_ascii=False), encoding="utf-8")
        port = _free_port()
        srv = portfolio_web.make_server("127.0.0.1", port, str(data_file))
        token = portfolio_web._ensure_token()
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            status, body = _hit(f"http://127.0.0.1:{port}/api/positions", token=token)
            assert status == 200
            j = json.loads(body)
            assert len(j["data"]["positions"]) == 1
            assert len(j["data"]["watchlist"]) == 1
        finally:
            srv.shutdown()
            srv.server_close()

    def test_get_one_found(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            _hit(f"{base}/api/positions", "POST", {"action": "add_position", "code": "sh600989",
                                                    "name": "宝丰", "cost": 18.5, "quantity": 1000},
                 token=token)
            status, body = _hit(f"{base}/api/positions/sh600989", token=token)
            assert status == 200
            j = json.loads(body)
            assert j["ok"]
            assert j["data"]["position"]["code"] == "sh600989"

    def test_get_one_not_found_404(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions/nope", token=token)
            assert status == 404
            j = json.loads(body)
            assert not j["ok"]
            assert j["error"] == "not_found"

    def test_unknown_path_404(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/nope", token=token)
            assert status == 404
            j = json.loads(body)
            assert j["error"] == "not_found"

    def test_wrong_method_405(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "DELETE", token=token)
            assert status == 405
            j = json.loads(body)
            assert j["error"] == "method_not_allowed"

    def test_post_wrong_content_type_415(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", body={"x": 1},
                                content_type="text/plain", token=token)
            assert status == 415
            j = json.loads(body)
            assert j["error"] == "unsupported_media_type"

    def test_post_invalid_json_400(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", raw_body=b"not json{{{",
                                token=token)
            assert status == 400
            j = json.loads(body)
            assert j["error"] == "invalid_json"

    def test_post_empty_body_400(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", raw_body=b"", token=token)
            assert status == 400
            j = json.loads(body)
            assert j["error"] == "missing_action"

    def test_favicon_204(self, tmp_path):
        with running_server(tmp_path) as (base, _, _):
            status, body = _hit(f"{base}/favicon.ico")
            assert status == 204
            assert body == ""


# ═══════════════════════════════════════════════════════════════
# 8 个 action
# ═══════════════════════════════════════════════════════════════


class TestActions:
    def test_add_position_happy(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "add_position", "code": "sh600989",
                "name": "宝丰能源", "cost": 18.5, "quantity": 1000, "tags": ["长线", "能源"],
            }, token=token)
            assert status == 200
            j = json.loads(body)
            assert j["ok"]
            assert j["data"]["code"] == "sh600989"
            assert j["data"]["cost"] == 18.5
            assert j["data"]["quantity"] == 1000
            assert set(j["data"]["tags"]) == {"长线", "能源"}

    def test_add_position_missing_cost_400(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "add_position", "code": "sh600989", "quantity": 1000,
            }, token=token)
            assert status == 400
            assert json.loads(body)["error"] == "invalid_cost"

    def test_add_position_negative_quantity_400(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "add_position", "code": "sh600989", "cost": 18.5, "quantity": -1,
            }, token=token)
            assert status == 400
            assert json.loads(body)["error"] == "invalid_quantity"

    def test_add_position_string_quantity_400(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "add_position", "code": "sh600989", "cost": 18.5, "quantity": "abc",
            }, token=token)
            assert status == 400
            assert json.loads(body)["error"] == "invalid_quantity"

    def test_add_position_add_merges_cost_weighted(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            _hit(f"{base}/api/positions", "POST", {
                "action": "add_position", "code": "sh600989", "cost": 18.0, "quantity": 1000,
            }, token=token)
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "add_position", "code": "sh600989", "cost": 19.0, "quantity": 500,
            }, token=token)
            assert status == 200
            j = json.loads(body)
            # 加权 (18*1000 + 19*500)/1500 = 18.333
            assert abs(j["data"]["cost"] - 18.333) < 0.01
            assert j["data"]["quantity"] == 1500

    def test_reduce_position_happy(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            _hit(f"{base}/api/positions", "POST", {
                "action": "add_position", "code": "sh600989", "cost": 18.5, "quantity": 1000,
            }, token=token)
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "reduce_position", "code": "sh600989", "quantity": 300,
            }, token=token)
            assert status == 200
            j = json.loads(body)
            assert j["ok"]
            assert j["data"]["quantity"] == 700

    def test_reduce_position_quantity_zero_400(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "reduce_position", "code": "sh600989", "quantity": 0,
            }, token=token)
            assert status == 400
            assert json.loads(body)["error"] == "invalid_quantity"

    def test_reduce_position_negative_400(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "reduce_position", "code": "sh600989", "quantity": -10,
            }, token=token)
            assert status == 400

    def test_reduce_position_overflow_returns_null(self, tmp_path):
        """减仓超量 → manager 自动 pop 并返回 None；handler 透传 data: null"""
        with running_server(tmp_path) as (base, _, token):
            _hit(f"{base}/api/positions", "POST", {
                "action": "add_position", "code": "sh600989", "cost": 18.5, "quantity": 100,
            }, token=token)
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "reduce_position", "code": "sh600989", "quantity": 500,
            }, token=token)
            assert status == 200
            j = json.loads(body)
            assert j["data"] is None
            assert "position_removed" in (j.get("warn") or [])

    def test_remove_position_happy(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            _hit(f"{base}/api/positions", "POST", {
                "action": "add_position", "code": "sh600989", "cost": 18.5, "quantity": 1000,
            }, token=token)
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "remove_position", "code": "sh600989",
            }, token=token)
            assert status == 200
            assert json.loads(body)["data"] is True

    def test_remove_position_idempotent_false(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "remove_position", "code": "sh600989",
            }, token=token)
            assert status == 200
            assert json.loads(body)["data"] is False

    def test_update_position_partial(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            _hit(f"{base}/api/positions", "POST", {
                "action": "add_position", "code": "sh600989", "cost": 18.5, "quantity": 1000,
                "name": "宝丰", "tags": ["长线"],
            }, token=token)
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "update_position", "code": "sh600989", "name": "宝丰能源", "cost": 19.0,
            }, token=token)
            assert status == 200
            j = json.loads(body)
            assert j["data"]["name"] == "宝丰能源"
            assert j["data"]["cost"] == 19.0
            assert j["data"]["quantity"] == 1000  # 未改
            assert j["data"]["tags"] == ["长线"]  # 未改

    def test_update_position_no_fields_400(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            _hit(f"{base}/api/positions", "POST", {
                "action": "add_position", "code": "sh600989", "cost": 18.5, "quantity": 1000,
            }, token=token)
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "update_position", "code": "sh600989",
            }, token=token)
            assert status == 400
            assert json.loads(body)["error"] == "no_update_fields"

    def test_update_position_unknown_field_ignored(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            _hit(f"{base}/api/positions", "POST", {
                "action": "add_position", "code": "sh600989", "cost": 18.5, "quantity": 1000,
            }, token=token)
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "update_position", "code": "sh600989",
                "cost": 19.0, "hack_field": "evil",
            }, token=token)
            assert status == 200
            j = json.loads(body)
            assert j["data"]["cost"] == 19.0
            assert "hack_field" not in j["data"]

    def test_update_position_tags_warning(self, tmp_path):
        """update_position 带 tags 应有 warn 字段，提示整列表覆盖。"""
        with running_server(tmp_path) as (base, _, token):
            _hit(f"{base}/api/positions", "POST", {
                "action": "add_position", "code": "sh600989", "cost": 18.5, "quantity": 1000,
                "tags": ["长线", "能源"],
            }, token=token)
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "update_position", "code": "sh600989", "tags": ["短线"],
            }, token=token)
            assert status == 200
            j = json.loads(body)
            assert j["data"]["tags"] == ["短线"]
            assert "update_position_replaces_tags" in (j.get("warn") or [])

    def test_tag_position_merges(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            _hit(f"{base}/api/positions", "POST", {
                "action": "add_position", "code": "sh600989", "cost": 18.5, "quantity": 1000,
                "tags": ["长线"],
            }, token=token)
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "tag_position", "code": "sh600989", "tags": ["能源", "长线"],
            }, token=token)
            assert status == 200
            j = json.loads(body)
            # sorted 返回 manager 排序后的列表（Unicode 字节序，非中文笔画序）
            assert set(j["data"]["tags"]) == {"长线", "能源"}

    def test_tag_position_empty_400(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "tag_position", "code": "sh600989", "tags": [],
            }, token=token)
            assert status == 400
            assert json.loads(body)["error"] == "missing_tags"

    def test_untag_position_removes(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            _hit(f"{base}/api/positions", "POST", {
                "action": "add_position", "code": "sh600989", "cost": 18.5, "quantity": 1000,
                "tags": ["长线", "能源"],
            }, token=token)
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "untag_position", "code": "sh600989", "tags": ["能源"],
            }, token=token)
            assert status == 200
            j = json.loads(body)
            assert j["data"]["tags"] == ["长线"]

    def test_add_watch_with_zero_target_400(self, tmp_path):
        """0 陷阱防护：add_watch 的 target_buy=0 / target_sell=0 显式 400。"""
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "add_watch", "code": "sh601318", "target_buy": 0,
            }, token=token)
            assert status == 400
            assert json.loads(body)["error"] == "invalid_target_buy"

    def test_add_watch_negative_target_400(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "add_watch", "code": "sh601318", "target_sell": -5,
            }, token=token)
            assert status == 400
            assert json.loads(body)["error"] == "invalid_target_sell"

    def test_add_watch_happy(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "add_watch", "code": "sh601318", "name": "中国平安",
                "target_buy": 50.0, "target_sell": 70.0,
            }, token=token)
            assert status == 200
            j = json.loads(body)
            assert j["data"]["code"] == "sh601318"
            assert j["data"]["target_buy"] == 50.0

    def test_add_watch_omit_targets(self, tmp_path):
        """不传 target_buy/target_sell 视为 0 = 跳过。"""
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "add_watch", "code": "sh601318",
            }, token=token)
            assert status == 200
            j = json.loads(body)
            assert j["data"]["target_buy"] == 0
            assert j["data"]["target_sell"] == 0

    def test_remove_watch_idempotent(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "remove_watch", "code": "sh601318",
            }, token=token)
            assert status == 200
            assert json.loads(body)["data"] is False

    def test_update_watch_happy(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            _hit(f"{base}/api/positions", "POST", {
                "action": "add_watch", "code": "sh601318", "name": "平安",
                "target_buy": 50.0, "target_sell": 70.0,
            }, token=token)
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "update_watch", "code": "sh601318", "target_buy": 55.0,
            }, token=token)
            assert status == 200
            j = json.loads(body)
            assert j["data"]["target_buy"] == 55.0
            assert j["data"]["target_sell"] == 70.0  # unchanged

    def test_update_watch_not_found_returns_null(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "update_watch", "code": "nope", "target_buy": 10,
            }, token=token)
            assert status == 200
            assert json.loads(body)["data"] is None

    def test_update_watch_no_fields_400(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "update_watch", "code": "sh601318",
            }, token=token)
            assert status == 400
            assert json.loads(body)["error"] == "no_update_fields"

    def test_unknown_action_400(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "drop_table", "code": "x",
            }, token=token)
            assert status == 400
            assert json.loads(body)["error"] == "unknown_action"

    def test_missing_action_400(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", {"code": "sh600989"}, token=token)
            assert status == 400
            assert json.loads(body)["error"] == "missing_action"

    def test_missing_code_400(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "add_position", "cost": 18.5, "quantity": 1000,
            }, token=token)
            assert status == 400
            assert json.loads(body)["error"] == "missing_code"

    def test_tags_string_csv(self, tmp_path):
        """tags 既接受 list 也接受逗号分隔字符串。"""
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "add_position", "code": "sh600989", "cost": 18.5, "quantity": 1000,
                "tags": "长线, 能源",
            }, token=token)
            assert status == 200
            j = json.loads(body)
            assert set(j["data"]["tags"]) == {"长线", "能源"}


# ═══════════════════════════════════════════════════════════════
# HTML 页面
# ═══════════════════════════════════════════════════════════════


class TestPage:
    def test_index_returns_200_html(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            # 走原始 http.client 以便看 Content-Type
            conn = HTTPConnection("127.0.0.1", int(base.split(":")[-1].rstrip("/")), timeout=5)
            try:
                conn.request("GET", "/", headers={"Authorization": f"Bearer {token}"})
                r = conn.getresponse()
                assert r.status == 200
                ct = r.getheader("Content-Type")
                assert ct.startswith("text/html")
                body = r.read().decode("utf-8")
                assert "<form" in body
                assert 'id="action"' in body
                assert 'list="codes"' in body
            finally:
                conn.close()

    def test_index_datalist_includes_known_code(self, tmp_path):
        data_file = tmp_path / "portfolio.json"
        data_file.write_text(json.dumps({
            "version": 2,
            "positions": [{"code": "sh600989", "name": "宝丰能源", "cost": 18.5,
                           "quantity": 1000, "buy_date": "2025-03-15", "tags": []}],
            "watchlist": [],
        }, ensure_ascii=False), encoding="utf-8")
        port = _free_port()
        srv = portfolio_web.make_server("127.0.0.1", port, str(data_file))
        token = portfolio_web._ensure_token()
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            conn = HTTPConnection("127.0.0.1", port, timeout=5)
            try:
                conn.request("GET", "/", headers={"Authorization": f"Bearer {token}"})
                r = conn.getresponse()
                body = r.read().decode("utf-8")
                assert 'value="sh600989"' in body
                assert "宝丰能源" in body
            finally:
                conn.close()
        finally:
            srv.shutdown()
            srv.server_close()


# ═══════════════════════════════════════════════════════════════
# 并发
# ═══════════════════════════════════════════════════════════════


class TestConcurrency:
    def test_concurrent_add_positions(self, tmp_path):
        """10 线程同时 add_position（不同 code）+ 5 线程同 code → 数据一致。"""
        with running_server(tmp_path) as (base, _, token):
            errors: list = []

            def hit_add(code: str, cost: float, qty: int):
                try:
                    s, b = _hit(f"{base}/api/positions", "POST", {
                        "action": "add_position", "code": code, "cost": cost, "quantity": qty,
                    }, token=token)
                    if s != 200:
                        errors.append((code, s, b))
                except Exception as e:
                    errors.append((code, "exc", str(e)))

            threads = []
            # 10 线程，不同 code
            for i in range(10):
                t = threading.Thread(target=hit_add, args=(f"sh60000{i}", 10.0, 100))
                threads.append(t)
            # 5 线程，同 code 累加
            for _ in range(5):
                t = threading.Thread(target=hit_add, args=("sh688888", 50.0, 10))
                threads.append(t)
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert not errors, f"some requests failed: {errors}"

            # 验证落库：sh688888 应该是 50 股 (5*10)
            s, b = _hit(f"{base}/api/positions/sh688888", token=token)
            j = json.loads(b)
            assert j["data"]["position"]["quantity"] == 50

            # sh600000..sh600009 应有 10 条
            s, b = _hit(f"{base}/api/positions", token=token)
            j = json.loads(b)
            assert len(j["data"]["positions"]) == 11

    def test_concurrent_mixed_reads_writes(self, tmp_path):
        """并发混合：写 + 读不应打挂 server。"""
        with running_server(tmp_path) as (base, _, token):
            stop = threading.Event()
            errors: list = []

            def writer():
                for i in range(20):
                    if stop.is_set():
                        return
                    try:
                        _hit(f"{base}/api/positions", "POST", {
                            "action": "add_position", "code": f"sh6000{i % 5:02d}",
                            "cost": 10.0, "quantity": 10,
                        }, token=token)
                    except Exception as e:
                        errors.append(("write", str(e)))

            def reader():
                for _ in range(40):
                    if stop.is_set():
                        return
                    try:
                        _hit(f"{base}/api/positions", token=token)
                    except Exception as e:
                        errors.append(("read", str(e)))

            threads = [
                threading.Thread(target=writer),
                threading.Thread(target=writer),
                threading.Thread(target=reader),
                threading.Thread(target=reader),
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            stop.set()
            assert not errors, f"errors: {errors[:3]}"


# ═══════════════════════════════════════════════════════════════
# 端到端 CRUD 生命周期
# ═══════════════════════════════════════════════════════════════


class TestEndToEnd:
    def test_full_crud_lifecycle(self, tmp_path):
        with running_server(tmp_path) as (base, data_file, token):
            # 1. add
            s, b = _hit(f"{base}/api/positions", "POST", {
                "action": "add_position", "code": "sh600989", "name": "宝丰",
                "cost": 18.5, "quantity": 1000, "tags": ["长线", "能源"],
            }, token=token)
            assert s == 200
            # 2. read
            s, b = _hit(f"{base}/api/positions/sh600989", token=token)
            assert json.loads(b)["data"]["position"]["code"] == "sh600989"
            # 3. update
            s, b = _hit(f"{base}/api/positions", "POST", {
                "action": "update_position", "code": "sh600989", "cost": 19.0,
            }, token=token)
            assert json.loads(b)["data"]["cost"] == 19.0
            # 4. tag
            s, b = _hit(f"{base}/api/positions", "POST", {
                "action": "tag_position", "code": "sh600989", "tags": ["价值"],
            }, token=token)
            assert "价值" in json.loads(b)["data"]["tags"]
            # 5. add watch
            s, b = _hit(f"{base}/api/positions", "POST", {
                "action": "add_watch", "code": "sz000807", "name": "云铝",
                "target_buy": 12.0, "target_sell": 18.0,
            }, token=token)
            assert s == 200
            # 6. reduce
            s, b = _hit(f"{base}/api/positions", "POST", {
                "action": "reduce_position", "code": "sh600989", "quantity": 500,
            }, token=token)
            assert json.loads(b)["data"]["quantity"] == 500
            # 7. 文件落盘验证（重启 manager 读取同一文件）
            pm = PortfolioManager(path=str(data_file))
            p = pm.get_position("sh600989")
            assert p["quantity"] == 500
            assert p["cost"] == 19.0
            assert "价值" in p["tags"]
            w = pm.get_watch("sz000807")
            assert w["target_buy"] == 12.0
            # 8. remove all
            _hit(f"{base}/api/positions", "POST", {"action": "remove_position", "code": "sh600989"},
                 token=token)
            _hit(f"{base}/api/positions", "POST", {"action": "remove_watch", "code": "sz000807"},
                 token=token)
            pm2 = PortfolioManager(path=str(data_file))
            assert pm2.get_positions() == []
            assert pm2.get_watchlist() == []


# ═══════════════════════════════════════════════════════════════
# Body 大小限制
# ═══════════════════════════════════════════════════════════════


class TestBodyLimit:
    def test_body_too_large(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            # 9 KB > 8 KB limit
            huge = b"x" * (9 * 1024)
            req = urllib.request.Request(f"{base}/api/positions", data=huge, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Bearer {token}")
            try:
                r = urllib.request.urlopen(req, timeout=5)
                status, body = r.status, r.read().decode()
            except urllib.error.HTTPError as e:
                status, body = e.code, e.read().decode()
            assert status in (400, 500)
            j = json.loads(body)
            assert j["ok"] is False


# ═══════════════════════════════════════════════════════════════
# 模块级单元测试（不动 server）
# ═══════════════════════════════════════════════════════════════


class TestModuleLevel:
    def test_version_format(self):
        """版本号遵循 x.y.z。"""
        import re
        assert re.match(r"^\d+\.\d+\.\d+$", portfolio_web.VERSION)

    def test_allowed_actions_count(self):
        assert len(portfolio_web.ALLOWED_ACTIONS) == 9

    def test_max_body_bytes_sane(self):
        assert portfolio_web.MAX_BODY_BYTES >= 1024
        assert portfolio_web.MAX_BODY_BYTES <= 1024 * 1024


# ═══════════════════════════════════════════════════════════════
# Bearer Token 认证
# ═══════════════════════════════════════════════════════════════


class TestAuth:
    def test_get_without_token_returns_401(self, tmp_path):
        with running_server(tmp_path) as (base, _, _):
            status, body = _hit(f"{base}/api/positions")
            assert status == 401
            j = json.loads(body)
            assert j["error"] == "unauthorized"

    def test_post_without_token_returns_401(self, tmp_path):
        with running_server(tmp_path) as (base, _, _):
            status, body = _hit(f"{base}/api/positions", "POST",
                                {"action": "add_position", "code": "sh600989",
                                 "cost": 18.5, "quantity": 1000})
            assert status == 401
            j = json.loads(body)
            assert j["error"] == "unauthorized"

    def test_get_with_wrong_token_returns_401(self, tmp_path):
        with running_server(tmp_path) as (base, _, _):
            status, body = _hit(f"{base}/api/positions", token="wrong-token")
            assert status == 401

    def test_get_with_valid_token_returns_200(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", token=token)
            assert status == 200

    def test_post_with_valid_token_returns_200(self, tmp_path):
        with running_server(tmp_path) as (base, _, token):
            status, body = _hit(f"{base}/api/positions", "POST", {
                "action": "add_position", "code": "sh600989",
                "cost": 18.5, "quantity": 1000,
            }, token=token)
            assert status == 200

    def test_health_no_token_returns_200(self, tmp_path):
        """health 端点免认证。"""
        with running_server(tmp_path) as (base, _, _):
            status, body = _hit(f"{base}/api/health")
            assert status == 200
            j = json.loads(body)
            assert j["ok"] is True

    def test_favicon_no_token_returns_204(self, tmp_path):
        """favicon 端点免认证。"""
        with running_server(tmp_path) as (base, _, _):
            status, body = _hit(f"{base}/favicon.ico")
            assert status == 204

    def test_token_persisted_to_file(self, tmp_path):
        """token 应写入文件且权限 0o600。"""
        import stat as _stat
        token = portfolio_web._ensure_token()
        assert portfolio_web._TOKEN_FILE.exists()
        stored = portfolio_web._TOKEN_FILE.read_text(encoding="utf-8").strip()
        assert stored == token
        mode = portfolio_web._TOKEN_FILE.stat().st_mode
        assert mode & 0o777 == 0o600

    def test_token_idempotent(self, tmp_path):
        """多次调用 _ensure_token 返回相同值。"""
        t1 = portfolio_web._ensure_token()
        t2 = portfolio_web._ensure_token()
        assert t1 == t2

    def test_collect_code_name_map_dedup(self, tmp_path, monkeypatch):
        """扫多个数据源时 code 应去重保序。"""
        from pathlib import Path
        scripts_data = Path(portfolio_web._SCRIPTS_DIR) / "data"
        pairs = portfolio_web._collect_code_name_map()
        codes = [c for c, _ in pairs]
        # 去重
        assert len(codes) == len(set(codes))
        # 全部小写
        assert all(c == c.lower() for c in codes)
        # portfolio_example.json 中的 sh600989 应在前
        assert "sh600989" in codes
