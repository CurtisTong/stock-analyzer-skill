"""
持仓录入 Web 服务主应用模块。

监听 127.0.0.1:8765，提供：
- GET  /                  浏览器表单页（内联 HTML + vanilla JS）
- GET  /api/health        健康检查
- GET  /api/positions     列出全部持仓 + 自选
- GET  /api/positions/<c> 查询单只
- POST /api/positions     8 个 action 的统一入口
- GET  /favicon.ico       204

启动：
    python3 scripts/portfolio_web.py [--host 127.0.0.1] [--port 8765]
"""

import argparse
import hmac
import html
import json
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .dispatch import dispatch
from .templates import INDEX_HTML_TEMPLATE
from .utils import (
    _collect_code_name_map,
    _ensure_token,
    _err,
    _format_notify,
    _get_notifier,
    _get_pm,
    _is_trading_hours,
    _log_lock,
    _monitor_interval,
    _monitor_last_result,
    _monitor_loop,
    _notify_async,
    _notify_enabled,
    _ok,
    _reset_pm_for_tests,
    _server_start,
    MAX_BODY_BYTES,
)

__all__ = ["make_server", "Handler", "VERSION"]

VERSION = "2.0.0"

# 模块级状态
_data_file = None
_monitor_enabled = False
_monitor_thread = None
_virtual_mode = False


class Handler(BaseHTTPRequestHandler):
    """HTTP 请求处理器。"""

    server_version = f"PortfolioWeb/{VERSION}"
    sys_version = ""

    def log_message(self, format, *args):
        """抑制默认 stderr 日志。"""
        with _log_lock:
            sys.stderr.write(
                f"[{datetime.now().strftime('%H:%M:%S')}] {self.address_string()} {format % args}\n"
            )
            sys.stderr.flush()

    def _write(
        self,
        status: int,
        body: bytes,
        content_type: str = "application/json; charset=utf-8",
    ):
        """写入响应。"""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        try:
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # 客户端已断开，忽略

    def _write_json(self, status: int, payload: dict):
        """写入 JSON 响应。"""
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._write(status, body)

    def _read_body(self) -> bytes:
        """读取请求体。"""
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return b""
        if length > MAX_BODY_BYTES:
            raise ValueError(f"body too large: {length} > {MAX_BODY_BYTES}")
        return self.rfile.read(length)

    def _send_method_not_allowed(self, allowed: str):
        """发送 405 响应。"""
        self._write_json(
            HTTPStatus.METHOD_NOT_ALLOWED,
            _err("method_not_allowed", 405, f"allowed: {allowed}"),
        )

    def _check_auth(self) -> bool:
        """校验 Authorization: Bearer <token>（API）或 URL ?token=<token>（仅页面导航）。"""
        token = _ensure_token()
        # 优先检查 Authorization 头（API 调用，常量时间比较防时序攻击）
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and hmac.compare_digest(auth[7:].strip(), token):
            return True
        # 回退检查 URL query parameter（仅限页面导航，不用于 API）
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/":
            qs = parse_qs(urlparse(self.path).query)
            url_token = (qs.get("token") or [None])[0]
            if url_token and hmac.compare_digest(url_token.strip(), token):
                return True
        self._write_json(
            HTTPStatus.UNAUTHORIZED,
            _err("unauthorized", 401, "missing or invalid Bearer token"),
        )
        return False

    def do_GET(self):
        """处理 GET 请求。"""
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path not in ("/api/health", "/favicon.ico") and not self._check_auth():
            return
        try:
            if path == "/" or path == "":
                self._serve_index()
            elif path == "/api/health":
                self._serve_health()
            elif path == "/api/positions":
                self._serve_list()
            elif path == "/api/monitor":
                self._serve_monitor()
            elif path == "/api/trades":
                self._serve_trades()
            elif path.startswith("/api/positions/"):
                self._serve_get_one(path[len("/api/positions/") :])
            elif path == "/favicon.ico":
                self._write(HTTPStatus.NO_CONTENT, b"", "image/x-icon")
            else:
                self._write_json(HTTPStatus.NOT_FOUND, _err("not_found", 404, path))
        except Exception as e:
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                _err("internal_error", 500, f"{type(e).__name__}: {e}"),
            )

    def do_HEAD(self):
        """处理 HEAD 请求。"""
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path not in ("/api/health", "/favicon.ico") and not self._check_auth():
            return
        if path in (
            "/",
            "/api/health",
            "/api/positions",
            "/api/monitor",
            "/favicon.ico",
        ) or path.startswith("/api/positions/"):
            self._write(HTTPStatus.OK, b"", "application/json; charset=utf-8")
        else:
            self._write(HTTPStatus.NOT_FOUND, b"", "application/json; charset=utf-8")

    def do_POST(self):
        """处理 POST 请求。"""
        if not self._check_auth():
            return
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/positions":
            self._write_json(HTTPStatus.NOT_FOUND, _err("not_found", 404, path))
            return

        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            self._write_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                _err(
                    "unsupported_media_type",
                    415,
                    "Content-Type must be application/json",
                ),
            )
            return

        try:
            raw = self._read_body()
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError as e:
            self._write_json(HTTPStatus.BAD_REQUEST, _err("invalid_json", 400, str(e)))
            return

        try:
            from .utils import _lock

            with _lock:
                pm = _get_pm()
                if body.get("action") == "reduce_position" and body.get("code"):
                    p = pm.get_position(body["code"])
                    if p:
                        body["_name"] = p.get("name") or body["code"]
                result = dispatch(pm, body)
        except Exception as e:
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                _err("internal_error", 500, f"{type(e).__name__}: {e}"),
            )
            return

        status = HTTPStatus.OK if result.get("ok") else self._status_from_error(result)
        self._write_json(status, result)

        if result.get("ok") and body.get("action"):
            title, body_text = _format_notify(body["action"], result, body)
            _notify_async(title, body_text)

    def _status_from_error(self, result: dict) -> HTTPStatus:
        """从错误结果中提取 HTTP 状态码。"""
        code = result.get("code") or 400
        try:
            return HTTPStatus(code)
        except ValueError:
            return HTTPStatus.BAD_REQUEST

    def _serve_health(self):
        """健康检查。"""
        from .utils import _lock

        with _lock:
            pm = _get_pm()
            is_example = pm.is_example
        nm = _get_notifier()
        payload = {
            "ok": True,
            "version": VERSION,
            "uptime_sec": round(time.time() - _server_start, 1),
            "example": is_example,
            "notify": {
                "enabled": _notify_enabled,
                "channels": nm.get_active_channels() if nm else [],
            },
            "monitor": {
                "enabled": _monitor_enabled,
                "interval": _monitor_interval,
                "trading_hours": _is_trading_hours(),
                "last_alerts": (_monitor_last_result or {}).get("alerts", 0),
            },
        }
        self._write_json(HTTPStatus.OK, payload)

    def _serve_index(self):
        """首页。"""
        pairs = _collect_code_name_map()
        datalist = "\n".join(
            (
                f'<option value="{html.escape(c)}">{html.escape(c)} — {html.escape(n)}</option>'
                if n
                else f'<option value="{html.escape(c)}"></option>'
            )
            for c, n in pairs
        )
        page = INDEX_HTML_TEMPLATE.replace("__DATALIST__", datalist).replace(
            "__VERSION__", VERSION
        )
        body = page.encode("utf-8")
        self._write(HTTPStatus.OK, body, "text/html; charset=utf-8")

    def _serve_list(self):
        """列表接口（附带实时行情）。"""
        from .utils import _lock, _virtual_mode

        with _lock:
            pm = _get_pm()
            data = pm.to_dict()
            summary = pm.summary()

        positions = data.get("positions", [])
        watchlist = data.get("watchlist", [])

        # 批量获取实时行情
        all_codes = [p["code"] for p in positions] + [w["code"] for w in watchlist]
        quote_map = {}
        if all_codes:
            try:
                from data import get_quotes

                quotes = get_quotes(all_codes, use_cache=True)
                quote_map = {q.code: q for q in quotes if q}
            except Exception:
                pass  # 行情获取失败不影响列表

        # 为持仓附加行情数据
        for p in positions:
            q = quote_map.get(p["code"])
            if q:
                p["current_price"] = round(q.price, 3) if q.price else None
                p["change_pct"] = round(q.change_pct, 2) if q.change_pct else None
                cost = p.get("cost", 0)
                qty = p.get("quantity", 0)
                if q.price and cost and qty:
                    p["market_value"] = round(q.price * qty, 2)
                    p["profit_pct"] = (
                        round((q.price - cost) / cost * 100, 2) if cost else 0
                    )
                    p["profit_amount"] = round((q.price - cost) * qty, 2)
                else:
                    p["market_value"] = None
                    p["profit_pct"] = None
                    p["profit_amount"] = None
            else:
                p["current_price"] = None
                p["change_pct"] = None
                p["market_value"] = None
                p["profit_pct"] = None
                p["profit_amount"] = None

        # 为自选附加行情数据
        for w in watchlist:
            q = quote_map.get(w["code"])
            if q:
                w["current_price"] = round(q.price, 3) if q.price else None
                w["change_pct"] = round(q.change_pct, 2) if q.change_pct else None
                tb = w.get("target_buy", 0)
                ts = w.get("target_sell", 0)
                if q.price and tb:
                    w["buy_gap_pct"] = round((q.price - tb) / tb * 100, 2)
                else:
                    w["buy_gap_pct"] = None
                if q.price and ts:
                    w["sell_gap_pct"] = round((q.price - ts) / ts * 100, 2)
                else:
                    w["sell_gap_pct"] = None
            else:
                w["current_price"] = None
                w["change_pct"] = None
                w["buy_gap_pct"] = None
                w["sell_gap_pct"] = None

        payload = {
            "ok": True,
            "data": {
                "positions": positions,
                "watchlist": watchlist,
                "summary": summary,
                "virtual": _virtual_mode,
            },
        }
        self._write_json(HTTPStatus.OK, payload)

    def _serve_get_one(self, code: str):
        """查询单只。"""
        if not code:
            self._write_json(HTTPStatus.NOT_FOUND, _err("not_found", 404, "empty code"))
            return
        from .utils import _lock

        with _lock:
            pm = _get_pm()
            pos = pm.get_position(code)
            watch = pm.get_watch(code)
        if pos is None and watch is None:
            self._write_json(HTTPStatus.NOT_FOUND, _err("not_found", 404, code))
            return
        data = {"position": pos, "watch": watch}
        self._write_json(HTTPStatus.OK, _ok(data))

    def _serve_monitor(self):
        """监控状态。"""
        payload = {
            "ok": True,
            "data": {
                "enabled": _monitor_enabled,
                "interval": _monitor_interval,
                "trading_hours": _is_trading_hours(),
                "last_result": _monitor_last_result,
            },
        }
        self._write_json(HTTPStatus.OK, payload)

    def _serve_trades(self):
        """交易日志接口。"""
        try:
            from portfolio.trade_log import TradeLog

            tl = TradeLog()
            history = tl.query()
            stats = tl.stats()
            payload = {
                "ok": True,
                "data": {
                    "history": history[-50:],  # 最近 50 条
                    "stats": stats,
                },
            }
            self._write_json(HTTPStatus.OK, payload)
        except Exception:
            self._write_json(
                HTTPStatus.OK,
                {"ok": True, "data": {"history": [], "stats": {}}},
            )

    def do_PUT(self):
        self._send_method_not_allowed("GET, POST")

    def do_DELETE(self):
        self._send_method_not_allowed("GET, POST")

    def do_PATCH(self):
        self._send_method_not_allowed("GET, POST")


def make_server(
    host: str, port: int, data_file: Optional[str] = None, virtual: bool = False
) -> ThreadingHTTPServer:
    """构造 ThreadingHTTPServer 实例（不启动）。"""
    import portfolio.web.utils as utils

    utils._data_file = data_file
    utils._virtual_mode = virtual
    _reset_pm_for_tests()
    ThreadingHTTPServer.allow_reuse_address = True
    return ThreadingHTTPServer((host, port), Handler)


def main():
    """主入口。"""
    global _monitor_enabled, _monitor_thread, _monitor_interval

    parser = argparse.ArgumentParser(
        description="持仓录入 Web 服务（仅本机，零依赖 stdlib http.server）",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）"
    )
    parser.add_argument("--port", type=int, default=8765, help="监听端口（默认 8765）")
    parser.add_argument(
        "--data-file",
        default=None,
        help="portfolio.json 路径（默认 scripts/data/portfolio.json）",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        default=False,
        help="启动后不自动打开浏览器（默认自动打开）",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        default=True,
        help="启用持仓变更推送（默认开启，自动读取 notification.yaml）",
    )
    parser.add_argument(
        "--no-notify", dest="notify", action="store_false", help="禁用持仓变更推送"
    )
    parser.add_argument(
        "--monitor", action="store_true", default=True, help="启用后台监控（默认开启）"
    )
    parser.add_argument(
        "--no-monitor", dest="monitor", action="store_false", help="禁用后台监控"
    )
    parser.add_argument(
        "--monitor-interval", type=int, default=300, help="监控检查间隔秒数（默认 300）"
    )
    parser.add_argument(
        "--allow-public-bind",
        action="store_true",
        help="允许绑定到 0.0.0.0（默认拒绝）",
    )
    parser.add_argument(
        "--virtual",
        action="store_true",
        default=False,
        help="启动虚拟持仓模式（模拟盘）",
    )
    args = parser.parse_args()

    if args.host == "0.0.0.0" and not args.allow_public_bind:
        print("ERROR: 绑定 0.0.0.0 需显式 --allow-public-bind 参数", file=sys.stderr)
        sys.exit(1)

    try:
        server = make_server(args.host, args.port, args.data_file, virtual=args.virtual)
    except OSError as e:
        print(f"ERROR: 无法启动 ({args.host}:{args.port}): {e}", file=sys.stderr)
        print(f"提示: 用 `lsof -i:{args.port}` 查看占用进程", file=sys.stderr)
        sys.exit(1)

    bound_host, bound_port = server.server_address
    token = _ensure_token()
    mode_label = "虚拟持仓（模拟盘）" if args.virtual else "实盘持仓"
    print(
        f"Portfolio Web 启动: http://{bound_host}:{bound_port}/?token={token}",
        flush=True,
    )
    print(f"  模式: {mode_label}", flush=True)
    print(f"  Token: {token}", flush=True)
    print(
        f"  数据文件: {args.data_file or Path(__file__).parent.parent.parent / 'data' / 'portfolio.json'}",
        flush=True,
    )

    if not args.no_open:
        url = f"http://{bound_host}:{bound_port}/?token={token}"
        try:
            webbrowser.open(url)
            print(f"  浏览器已打开: {url}", flush=True)
        except Exception:
            print(f"  浏览器打开失败，请手动访问: {url}", flush=True)

    import portfolio.web.utils as _utils

    if args.notify:
        _utils._notify_enabled = True
        nm = _get_notifier()
        if nm:
            channels = nm.get_active_channels()
            print(f"  通知推送: ✅ 已接入 ({', '.join(channels)})", flush=True)
        else:
            print(
                "  通知推送: ⚠ 未配置通道（编辑 scripts/config/notification.yaml 开启）",
                flush=True,
            )
    else:
        print("  通知推送: ❌ 已禁用", flush=True)

    if args.monitor:
        _monitor_enabled = True
        _monitor_interval = args.monitor_interval
        _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
        _monitor_thread.start()
    else:
        print("  后台监控: ❌ 已禁用", flush=True)

    print("  停止: Ctrl-C", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down…", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
