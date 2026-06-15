#!/usr/bin/env python3
"""持仓录入 Web 服务（零依赖 stdlib http.server）。

监听 127.0.0.1:8765，提供：

- ``GET  /``                  浏览器表单页（内联 HTML + vanilla JS）
- ``GET  /api/health``        健康检查
- ``GET  /api/positions``     列出全部持仓 + 自选
- ``GET  /api/positions/<c>`` 查询单只
- ``POST /api/positions``     8 个 action 的统一入口
- ``GET  /favicon.ico``       204

启动::

    python3 scripts/portfolio_web.py [--host 127.0.0.1] [--port 8765]
"""

import argparse
import json
import os
import secrets
import socket
import stat
import subprocess
import sys
import threading
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

# 让 python3 scripts/portfolio_web.py 从项目根运行也能找到 portfolio 包
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from portfolio import PortfolioManager  # noqa: E402

__all__ = ["make_server", "Handler", "VERSION"]

VERSION = "1.5.0"

# —— action 白名单 ——
ALLOWED_ACTIONS = {
    "add_position", "reduce_position", "remove_position",
    "update_position", "tag_position", "untag_position",
    "add_watch", "remove_watch", "update_watch",
}

POSITION_UPDATE_FIELDS = {"cost", "quantity", "name", "buy_date", "tags"}
POSITION_REQUIRED = {"add_position": ("code", "cost", "quantity")}

# —— 防御性常量 ——
MAX_BODY_BYTES = 8 * 1024


# ===== 模块级状态（进程内单例） =====
_pm: Optional[PortfolioManager] = None
# RLock 因为 do_GET 持锁调 _get_pm() 时内部还要再持锁——Lock 不可重入会死锁
_lock = threading.RLock()
_server_start = time.time()
_data_file: Optional[str] = None
_log_lock = threading.Lock()
_notify_enabled = False
_nm = None  # NotificationManager 懒加载
_monitor_enabled = False
_monitor_thread = None
_monitor_stop_event = threading.Event()
_monitor_interval = 300  # 默认 5 分钟检查一次
_monitor_last_result = None  # 最近一次监控结果
_token: Optional[str] = None  # Bearer token（_ensure_token 初始化）


# ===== Bearer Token 认证 =====
_TOKEN_DIR = Path.home() / ".config" / "stock-analyzer"
_TOKEN_FILE = _TOKEN_DIR / "portfolio_web.token"


def _ensure_token() -> str:
    """读取或生成 Bearer token，存储到 ~/.config/stock-analyzer/portfolio_web.token。

    文件权限 0o600，仅所有者可读写。
    """
    global _token
    if _token is not None:
        return _token

    _TOKEN_DIR.mkdir(parents=True, exist_ok=True)

    if _TOKEN_FILE.exists():
        stored = _TOKEN_FILE.read_text(encoding="utf-8").strip()
        if stored:
            _token = stored
            return _token

    _token = secrets.token_urlsafe(32)
    _TOKEN_FILE.write_text(_token + "\n", encoding="utf-8")
    _TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    return _token


# ===== 工具函数 =====
def _err(msg: str, code: int = 400, detail: str = "") -> dict:
    return {"ok": False, "error": msg, "code": code, "detail": detail}


def _ok(data: Any, warn: Optional[list] = None) -> dict:
    payload: dict = {"ok": True, "data": data}
    if warn:
        payload["warn"] = warn
    return payload


def _get_pm() -> PortfolioManager:
    global _pm
    with _lock:
        if _pm is None:
            _pm = PortfolioManager(path=_data_file)
        return _pm


def _reset_pm_for_tests() -> None:
    """测试用：清空单例。"""
    global _pm
    with _lock:
        _pm = None


def _parse_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _to_bool_str_list(v: Any) -> Optional[list]:
    """tags 字段：接受 list / 逗号分隔 str。"""
    if v is None:
        return None
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    return None


# ===== 通知推送 =====
def _get_notifier():
    """懒加载 NotificationManager。"""
    global _nm
    if _nm is not None:
        return _nm
    try:
        from monitor.manager import NotificationManager
        nm = NotificationManager()
        if nm.get_active_channels():
            _nm = nm
            return _nm
    except Exception:
        pass
    return None


def _notify_async(title: str, body: str) -> None:
    """后台线程发送通知，不阻塞响应。"""
    if not _notify_enabled:
        return
    nm = _get_notifier()
    if nm is None:
        return
    def _send():
        try:
            nm.send(title, body, throttle_key=f"portfolio_web:{title}")
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()


def _format_notify(action: str, result: dict, body: dict) -> tuple:
    """根据 action 和结果格式化通知标题和内容。返回 (title, body_text)。"""
    code = body.get("code", "")
    data = result.get("data")

    if action == "add_position":
        name = (data or {}).get("name") or code
        qty = (data or {}).get("quantity", 0)
        cost = (data or {}).get("cost", 0)
        return (f"📈 加仓: {name} {code}",
                f"+{qty}股 @¥{cost}，标签: {', '.join((data or {}).get('tags', [])) or '无'}")

    if action == "reduce_position":
        name = body.get("_name") or code
        qty = body.get("quantity", 0)
        if data is None:
            return (f"🗑 清仓(减仓归零): {name} {code}", f"减仓{qty}股后全部卖出")
        remaining = data.get("quantity", 0)
        return (f"📉 减仓: {name} {code}", f"-{qty}股，剩余{remaining}股")

    if action == "remove_position":
        return (f"🗑 清仓: {code}", "已从持仓中移除" if data else "未找到该持仓")

    if action == "update_position":
        fields = [k for k in body if k not in ("action", "code")]
        return (f"✏️ 更新: {code}", f"修改字段: {', '.join(fields)}")

    if action == "tag_position":
        tags = body.get("tags", [])
        return (f"🏷 加标签: {code}", f"追加: {', '.join(tags)}")

    if action == "untag_position":
        tags = body.get("tags", [])
        return (f"🏷 删标签: {code}", f"移除: {', '.join(tags)}")

    if action == "add_watch":
        name = (data or {}).get("name") or code
        tb = (data or {}).get("target_buy", 0)
        ts = (data or {}).get("target_sell", 0)
        parts = []
        if tb: parts.append(f"目标买¥{tb}")
        if ts: parts.append(f"目标卖¥{ts}")
        return (f"👁 加自选: {name} {code}", ', '.join(parts) or "已添加")

    if action == "remove_watch":
        return (f"👁 删自选: {code}", "已移除" if data else "未找到")

    return (f"📦 持仓操作: {action} {code}", str(data)[:100])


def _collect_code_name_map() -> list:
    """扫 portfolio.json + portfolio_example.json + sector_stocks.json
    返回 [(code, name_or_empty), ...]，去重保序。"""
    scripts_data = _SCRIPTS_DIR / "data"
    seen: dict = {}

    for fname in ("portfolio.json", "portfolio_example.json"):
        p = scripts_data / fname
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for entry in data.get("positions", []) + data.get("watchlist", []):
            code = (entry.get("code") or "").lower()
            name = entry.get("name") or ""
            if code and code not in seen:
                seen[code] = name

    # sector_stocks.json 形如 {sector: [code, ...]}，没有 name
    p = scripts_data / "sector_stocks.json"
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for v in data.values():
                if isinstance(v, list):
                    for code in v:
                        c = (code or "").lower()
                        if c and c not in seen:
                            seen[c] = ""
        except (OSError, json.JSONDecodeError):
            pass

    return [(c, n) for c, n in seen.items()]


# ===== 后台监控 =====
def _is_trading_hours() -> bool:
    """检查当前是否在交易时段。

    v1.7.1 起统一调用 data.config.is_trading_hours()，
    避免与 data/config.py 的实现双轨制漂移。该函数保留为薄包装
    以兼容既有调用点（portfolio_web.py 内 3 处）。
    """
    from data.config import is_trading_hours as _official_is_trading_hours
    return _official_is_trading_hours()


def _monitor_loop():
    """后台监控线程：扫描持仓+自选股，触发预警则推送。"""
    global _monitor_last_result
    import importlib
    try:
        alert_engine = importlib.import_module("monitor.alert_engine")
    except ImportError:
        print("  ⚠ 监控模块加载失败（monitor.alert_engine）", flush=True)
        return

    print("  📡 后台监控已启动（每 {} 秒检查一次）".format(_monitor_interval), flush=True)

    while not _monitor_stop_event.is_set():
        try:
            if _is_trading_hours():
                result = alert_engine.check_and_push(dry_run=not _notify_enabled)
                _monitor_last_result = result
                alerts = result.get("alerts", 0)
                pushed = result.get("pushed", 0)
                if alerts > 0:
                    ts = result.get("timestamp", "")
                    print(f"  [{ts}] 预警: {alerts} | 推送: {pushed}", flush=True)
            else:
                # 非交易时段静默
                pass
        except Exception as e:
            print(f"  ⚠ 监控异常: {e}", flush=True)

        # 等待间隔或停止信号
        _monitor_stop_event.wait(timeout=_monitor_interval)

    print("  📡 后台监控已停止", flush=True)


# ===== 业务分发（无锁外层；调用方持锁） =====
def _dispatch(pm: PortfolioManager, body: dict) -> dict:
    """根据 body['action'] 调用对应 manager 方法，返回响应 dict（不含 ok/code/error 字段）。"""
    if not isinstance(body, dict):
        return _err("invalid_body", 400, "request body must be a JSON object")

    action = body.get("action")
    if not action:
        return _err("missing_action", 400, "'action' field is required")
    if action not in ALLOWED_ACTIONS:
        return _err("unknown_action", 400,
                    f"action must be one of {sorted(ALLOWED_ACTIONS)}")

    code = body.get("code")
    if not code or not isinstance(code, str):
        return _err("missing_code", 400, "'code' is required (e.g. sh600989)")

    try:
        if action == "add_position":
            return _do_add_position(pm, body, code)
        if action == "reduce_position":
            return _do_reduce_position(pm, body, code)
        if action == "remove_position":
            return _do_remove_position(pm, code)
        if action == "update_position":
            return _do_update_position(pm, body, code)
        if action == "tag_position":
            return _do_tag_position(pm, body, code, untag=False)
        if action == "untag_position":
            return _do_tag_position(pm, body, code, untag=True)
        if action == "add_watch":
            return _do_add_watch(pm, body, code)
        if action == "remove_watch":
            return _do_remove_watch(pm, code)
        if action == "update_watch":
            return _do_update_watch(pm, body, code)
    except ValueError as e:
        return _err("validation_error", 400, str(e))
    except Exception as e:  # 兜底，handler 层会再捕获
        return _err("internal_error", 500, f"{type(e).__name__}: {e}")

    return _err("unknown_action", 400, "unreachable")  # pragma: no cover


def _do_add_position(pm: PortfolioManager, body: dict, code: str) -> dict:
    cost = _parse_float(body.get("cost"))
    if cost is None:
        return _err("invalid_cost", 400, "'cost' must be a number")
    if cost < 0:
        return _err("invalid_cost", 400, "'cost' must be >= 0")
    qty = _parse_int(body.get("quantity"))
    if qty is None:
        return _err("invalid_quantity", 400, "'quantity' must be an integer")
    if qty <= 0:
        return _err("invalid_quantity", 400, "'quantity' must be > 0")

    name = body.get("name", "") or ""
    buy_date = body.get("buy_date", "") or ""
    tags = _to_bool_str_list(body.get("tags")) or []

    result = pm.add_position(code, name, cost, qty,
                             buy_date=buy_date, tags=tags)
    return _ok(result)


def _do_reduce_position(pm: PortfolioManager, body: dict, code: str) -> dict:
    qty = _parse_int(body.get("quantity"))
    if qty is None:
        return _err("invalid_quantity", 400, "'quantity' must be an integer")
    if qty <= 0:
        return _err("invalid_quantity", 400, "'quantity' must be > 0")

    # manager 内部 ValueError 由 _dispatch 统一捕获
    result = pm.reduce_position(code, qty)
    return _ok(result, warn=["position_removed"] if result is None else None)


def _do_remove_position(pm: PortfolioManager, code: str) -> dict:
    removed = pm.remove_position(code)
    return _ok(removed)


def _do_update_position(pm: PortfolioManager, body: dict, code: str) -> dict:
    # 白名单过滤
    extra: dict = {}
    for k, v in body.items():
        if k in ("action", "code"):
            continue
        if k in POSITION_UPDATE_FIELDS:
            extra[k] = v
        # 非白名单字段静默忽略（不报错，保持 webhook 兼容）

    if not extra:
        return _err("no_update_fields", 400,
                    f"at least one of {sorted(POSITION_UPDATE_FIELDS)} is required")

    # 类型转换
    if "cost" in extra:
        c = _parse_float(extra["cost"])
        if c is None:
            return _err("invalid_cost", 400, "'cost' must be a number")
        extra["cost"] = c
    if "quantity" in extra:
        q = _parse_int(extra["quantity"])
        if q is None:
            return _err("invalid_quantity", 400, "'quantity' must be an integer")
        extra["quantity"] = q
    if "tags" in extra:
        tags = _to_bool_str_list(extra["tags"])
        if tags is None:
            return _err("invalid_tags", 400, "'tags' must be list or comma-separated string")
        extra["tags"] = tags

    result = pm.update_position(code, **extra)
    warn = ["update_position_replaces_tags"] if "tags" in extra else None
    return _ok(result, warn=warn)


def _do_tag_position(pm: PortfolioManager, body: dict, code: str, untag: bool) -> dict:
    tags = _to_bool_str_list(body.get("tags"))
    if not tags:
        verb = "untag" if untag else "tag"
        return _err("missing_tags", 400, f"'{verb}_position' requires non-empty 'tags'")
    method = pm.untag_position if untag else pm.tag_position
    result = method(code, *tags)
    return _ok(result)


def _do_add_watch(pm: PortfolioManager, body: dict, code: str) -> dict:
    name = body.get("name", "") or ""

    # 显式 0 拒绝（manager 会忽略 0，与"显式清零"语义不符）
    target_buy_raw = body.get("target_buy")
    target_sell_raw = body.get("target_sell")
    target_buy = 0
    target_sell = 0
    if target_buy_raw is not None:
        if isinstance(target_buy_raw, bool) or not isinstance(target_buy_raw, (int, float)):
            return _err("invalid_target_buy", 400, "'target_buy' must be a number (omit or null to skip)")
        if target_buy_raw == 0:
            return _err("invalid_target_buy", 400,
                        "'target_buy=0' is ignored by PortfolioManager; omit the field to leave unchanged")
        if target_buy_raw < 0:
            return _err("invalid_target_buy", 400, "'target_buy' must be > 0")
        target_buy = float(target_buy_raw)
    if target_sell_raw is not None:
        if isinstance(target_sell_raw, bool) or not isinstance(target_sell_raw, (int, float)):
            return _err("invalid_target_sell", 400, "'target_sell' must be a number (omit or null to skip)")
        if target_sell_raw == 0:
            return _err("invalid_target_sell", 400,
                        "'target_sell=0' is ignored by PortfolioManager; omit the field to leave unchanged")
        if target_sell_raw < 0:
            return _err("invalid_target_sell", 400, "'target_sell' must be > 0")
        target_sell = float(target_sell_raw)

    result = pm.add_watch(code, name=name,
                          target_buy=target_buy, target_sell=target_sell)
    return _ok(result)


def _do_remove_watch(pm: PortfolioManager, code: str) -> dict:
    removed = pm.remove_watch(code)
    return _ok(removed)


def _do_update_watch(pm: PortfolioManager, body: dict, code: str) -> dict:
    """修改自选股字段（name / target_buy / target_sell）。"""
    extra: dict = {}
    for k in ("name", "target_buy", "target_sell"):
        if k in body:
            extra[k] = body[k]
    if not extra:
        return _err("no_update_fields", 400,
                    "at least one of name/target_buy/target_sell is required")
    if "target_buy" in extra:
        if extra["target_buy"] == 0:
            return _err("invalid_target_buy", 400,
                        "'target_buy=0' is ignored by PortfolioManager; omit to leave unchanged")
        extra["target_buy"] = _parse_float(extra["target_buy"]) or 0
    if "target_sell" in extra:
        if extra["target_sell"] == 0:
            return _err("invalid_target_sell", 400,
                        "'target_sell=0' is ignored by PortfolioManager; omit to leave unchanged")
        extra["target_sell"] = _parse_float(extra["target_sell"]) or 0

    # PortfolioManager 没有 update_watch，用 add_watch 已存在时的覆盖语义
    existing = pm.get_watch(code)
    if existing is None:
        return _ok(None)  # 幂等
    name = extra.get("name", "") or ""
    tb = extra.get("target_buy", 0)
    ts = extra.get("target_sell", 0)
    result = pm.add_watch(code, name=name or existing.get("name", ""),
                          target_buy=tb or 0, target_sell=ts or 0)
    return _ok(result)


# ===== HTTP handler =====
class Handler(BaseHTTPRequestHandler):
    server_version = f"PortfolioWeb/{VERSION}"
    sys_version = ""

    # 抑制 BaseHTTPRequestHandler 默认 stderr 日志；需要时再单独开
    def log_message(self, format, *args):  # noqa: A002
        with _log_lock:
            sys.stderr.write(f"[{datetime.now().strftime('%H:%M:%S')}] {self.address_string()} {format % args}\n")
            sys.stderr.flush()

    # ---- helpers ----
    def _write(self, status: int, body: bytes, content_type: str = "application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
            self.wfile.flush()

    def _write_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._write(status, body)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return b""
        if length > MAX_BODY_BYTES:
            raise ValueError(f"body too large: {length} > {MAX_BODY_BYTES}")
        return self.rfile.read(length)

    def _send_method_not_allowed(self, allowed: str):
        self._write_json(HTTPStatus.METHOD_NOT_ALLOWED, _err("method_not_allowed", 405, f"allowed: {allowed}"))

    def _check_auth(self) -> bool:
        """校验 Authorization: Bearer <token>，不通过则写 401 响应并返回 False。"""
        token = _ensure_token()
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and auth[7:].strip() == token:
            return True
        self._write_json(HTTPStatus.UNAUTHORIZED,
                         _err("unauthorized", 401, "missing or invalid Bearer token"))
        return False

    # ---- GET ----
    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        # health / favicon 免认证
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
            elif path.startswith("/api/positions/"):
                self._serve_get_one(path[len("/api/positions/"):])
            elif path == "/favicon.ico":
                self._write(HTTPStatus.NO_CONTENT, b"", "image/x-icon")
            else:
                self._write_json(HTTPStatus.NOT_FOUND, _err("not_found", 404, path))
        except Exception as e:  # noqa: BLE001
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR,
                             _err("internal_error", 500, f"{type(e).__name__}: {e}"))

    def do_HEAD(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        # health / favicon 免认证
        if path not in ("/api/health", "/favicon.ico") and not self._check_auth():
            return
        if path in ("/", "/api/health", "/api/positions", "/api/monitor", "/favicon.ico") or path.startswith("/api/positions/"):
            self._write(HTTPStatus.OK, b"", "application/json; charset=utf-8")
        else:
            self._write(HTTPStatus.NOT_FOUND, b"", "application/json; charset=utf-8")

    def do_POST(self):
        if not self._check_auth():
            return
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/positions":
            self._write_json(HTTPStatus.NOT_FOUND, _err("not_found", 404, path))
            return

        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            self._write_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                             _err("unsupported_media_type", 415, "Content-Type must be application/json"))
            return

        try:
            raw = self._read_body()
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError as e:
            self._write_json(HTTPStatus.BAD_REQUEST,
                             _err("invalid_json", 400, str(e)))
            return

        try:
            with _lock:
                pm = _get_pm()
                # 缓存名称用于通知（reduce 前查一次）
                if body.get("action") == "reduce_position" and body.get("code"):
                    p = pm.get_position(body["code"])
                    if p:
                        body["_name"] = p.get("name") or body["code"]
                result = _dispatch(pm, body)
        except Exception as e:  # noqa: BLE001
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR,
                             _err("internal_error", 500, f"{type(e).__name__}: {e}"))
            return

        status = HTTPStatus.OK if result.get("ok") else self._status_from_error(result)
        self._write_json(status, result)

        # 成功的写操作 → 推送通知（不阻塞响应）
        if result.get("ok") and body.get("action"):
            title, body_text = _format_notify(body["action"], result, body)
            _notify_async(title, body_text)

    def _status_from_error(self, result: dict) -> HTTPStatus:
        code = result.get("code") or 400
        try:
            return HTTPStatus(code)
        except ValueError:
            return HTTPStatus.BAD_REQUEST

    # ---- concrete handlers ----
    def _serve_health(self):
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
        pairs = _collect_code_name_map()
        datalist = "\n".join(
            f'<option value="{c}">{c} — {n}</option>' if n else f'<option value="{c}"></option>'
            for c, n in pairs
        )
        html = INDEX_HTML_TEMPLATE.replace("__DATALIST__", datalist).replace("__VERSION__", VERSION)
        body = html.encode("utf-8")
        self._write(HTTPStatus.OK, body, "text/html; charset=utf-8")

    def _serve_list(self):
        with _lock:
            pm = _get_pm()
            data = pm.to_dict()
            summary = pm.summary()
        payload = {
            "ok": True,
            "data": {
                "positions": data.get("positions", []),
                "watchlist": data.get("watchlist", []),
                "summary": summary,
            },
        }
        self._write_json(HTTPStatus.OK, payload)

    def _serve_get_one(self, code: str):
        if not code:
            self._write_json(HTTPStatus.NOT_FOUND, _err("not_found", 404, "empty code"))
            return
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

    def do_PUT(self):  # noqa: N802
        self._send_method_not_allowed("GET, POST")

    def do_DELETE(self):  # noqa: N802
        self._send_method_not_allowed("GET, POST")

    def do_PATCH(self):  # noqa: N802
        self._send_method_not_allowed("GET, POST")


# —— HTML 模板（Claude Code 深色风格） ——
INDEX_HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Portfolio · Claude Code</title>
<style>
  :root {
    --bg: #0d1117; --surface: #161b22; --elevated: #1c2333;
    --border: #30363d; --border-focus: #e07a5f;
    --text: #e6edf3; --text-secondary: #8b949e; --text-muted: #6e7681;
    --accent: #e07a5f; --accent-hover: #c96b52; --accent-glow: rgba(224,122,95,.15);
    --success: #3fb950; --success-bg: rgba(63,185,80,.12);
    --error: #f85149; --error-bg: rgba(248,81,73,.12);
    --warning: #d29922; --warning-bg: rgba(210,153,34,.12);
    --mono: "SF Mono", "Fira Code", "JetBrains Mono", "Cascadia Code", monospace;
    --sans: -apple-system, "SF Pro Text", "PingFang SC", system-ui, sans-serif;
    --radius: 8px; --radius-sm: 6px;
  }
  * { box-sizing: border-box; margin: 0; }
  body { font-family: var(--sans); background: var(--bg); color: var(--text);
         font-size: 14px; line-height: 1.6; padding: 20px; -webkit-font-smoothing: antialiased; }
  .container { max-width: 740px; margin: 0 auto; }

  /* ── Header ── */
  header { display: flex; align-items: center; justify-content: space-between;
           margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
  header h1 { font-size: 18px; font-weight: 600; letter-spacing: -0.3px;
              display: flex; align-items: center; gap: 10px; }
  header h1 .logo { color: var(--accent); font-size: 20px; }
  .badge { font-family: var(--mono); font-size: 11px; color: var(--text-muted);
           background: var(--elevated); border: 1px solid var(--border);
           padding: 2px 8px; border-radius: 999px; }
  .btn-icon { background: none; border: 1px solid var(--border); color: var(--text-secondary);
              border-radius: var(--radius-sm); cursor: pointer; padding: 6px 12px;
              font-size: 13px; font-family: var(--sans); transition: all .15s;
              min-height: 34px; display: inline-flex; align-items: center; gap: 6px; }
  .btn-icon:hover { background: var(--elevated); color: var(--text); border-color: var(--text-muted); }

  /* ── Panels ── */
  .panel { background: var(--surface); border: 1px solid var(--border);
           border-radius: var(--radius); margin-bottom: 16px; overflow: hidden; }
  .panel-header { padding: 12px 16px; border-bottom: 1px solid var(--border);
                  display: flex; align-items: center; justify-content: space-between; }
  .panel-header h2 { font-size: 13px; font-weight: 600; color: var(--text-secondary);
                     text-transform: uppercase; letter-spacing: 0.5px; }
  .panel-body { padding: 0; overflow-x: auto; }

  /* ── Tables ── */
  table { width: 100%; border-collapse: collapse; font-size: 13px; font-family: var(--mono); }
  th { padding: 8px 14px; text-align: left; font-weight: 500; color: var(--text-muted);
       background: var(--elevated); font-size: 11px; text-transform: uppercase;
       letter-spacing: 0.5px; border-bottom: 1px solid var(--border); }
  td { padding: 10px 14px; border-bottom: 1px solid rgba(48,54,61,.5); color: var(--text); }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: rgba(224,122,95,.04); }
  .code-tag { font-family: var(--mono); font-size: 11px; color: var(--accent);
              background: var(--accent-glow); padding: 2px 7px; border-radius: 4px;
              margin-right: 4px; display: inline-block; }
  .empty { color: var(--text-muted); font-style: italic; padding: 20px 14px;
           text-align: center; font-size: 13px; }
  .positive { color: var(--success); } .negative { color: var(--error); }

  /* ── Forms ── */
  .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 16px; padding: 16px; }
  .form-group { display: flex; flex-direction: column; gap: 4px; }
  .form-group.full { grid-column: span 2; }
  label { font-size: 12px; color: var(--text-secondary); font-weight: 500; }
  input, select {
    font-family: var(--mono); font-size: 13px; color: var(--text);
    background: var(--elevated); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 8px 10px; width: 100%;
    transition: border-color .15s, box-shadow .15s;
  }
  input::placeholder { color: var(--text-muted); }
  input:focus, select:focus { outline: none; border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-glow); }
  select { cursor: pointer; appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M3 5l3 3 3-3' fill='none' stroke='%238b949e' stroke-width='1.5'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right 10px center; padding-right: 28px; }
  input[type="date"]::-webkit-calendar-picker-indicator { filter: invert(.7); cursor: pointer; }
  .required { color: var(--error); margin-left: 2px; }
  .warn { color: var(--warning); font-size: 11px; }

  /* ── Buttons ── */
  .btn-submit { width: 100%; padding: 10px 20px; font-family: var(--sans);
                font-size: 14px; font-weight: 500; color: #fff; background: var(--accent);
                border: 0; border-radius: var(--radius-sm); cursor: pointer;
                transition: background .15s, transform .1s; min-height: 40px; }
  .btn-submit:hover { background: var(--accent-hover); }
  .btn-submit:active { transform: scale(.98); }
  .btn-submit:disabled { background: var(--text-muted); cursor: not-allowed; transform: none; }
  .btn-copy { font-family: var(--mono); font-size: 11px; color: var(--text-secondary);
              background: var(--elevated); border: 1px solid var(--border);
              border-radius: var(--radius-sm); padding: 4px 10px; cursor: pointer;
              transition: all .15s; }
  .btn-copy:hover { color: var(--text); border-color: var(--text-muted); }

  /* ── Code block ── */
  pre { background: var(--bg); color: var(--text-secondary); padding: 14px 16px;
        font-family: var(--mono); font-size: 12px; line-height: 1.5;
        overflow-x: auto; border-top: 1px solid var(--border); }
  pre .kw { color: var(--accent); } pre .str { color: #a5d6ff; }

  /* ── Toast ── */
  .toast { position: fixed; top: 20px; left: 50%; transform: translateX(-50%) translateY(-8px);
           z-index: 1000; max-width: 440px; padding: 10px 16px; border-radius: var(--radius-sm);
           font-size: 13px; font-family: var(--sans); border: 1px solid;
           opacity: 0; transition: opacity .25s, transform .25s; pointer-events: none; }
  .toast.visible { opacity: 1; pointer-events: auto; transform: translateX(-50%) translateY(0); }
  .toast.ok { background: var(--success-bg); border-color: rgba(63,185,80,.3); color: var(--success); }
  .toast.err { background: var(--error-bg); border-color: rgba(248,81,73,.3); color: var(--error); }

  /* ── Destructive ── */
  .destructive { border: 1px solid rgba(248,81,73,.3); background: var(--error-bg);
                 padding: 10px 14px; border-radius: var(--radius-sm);
                 font-size: 12px; color: var(--error); font-family: var(--sans); }

  /* ── Responsive ── */
  @media (max-width: 480px) {
    body { padding: 12px; }
    .form-grid { grid-template-columns: 1fr; padding: 12px; }
    .form-group.full { grid-column: 1; }
    input, select { padding: 10px 12px; font-size: 16px; }
    .btn-submit { padding: 12px 20px; font-size: 16px; min-height: 44px; }
    .btn-icon, .btn-copy { min-height: 44px; min-width: 44px; }
    table { font-size: 12px; }
    th, td { padding: 8px 10px; }
    header h1 { font-size: 16px; }
  }
</style>
</head>
<body>
<div class="container">

  <header>
    <h1><span class="logo">◆</span> Portfolio <span class="badge">v__VERSION__</span></h1>
    <button class="btn-icon" id="refresh" aria-label="刷新列表">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 8A6 6 0 1 1 8 2"/><path d="M8 2v4l3-2"/></svg>
      刷新
    </button>
  </header>

  <div id="toast" class="toast" role="status" aria-live="polite"></div>

  <div class="panel">
    <div class="panel-header"><h2>持仓</h2></div>
    <div class="panel-body" id="positions" aria-live="polite"></div>
  </div>

  <div class="panel">
    <div class="panel-header"><h2>自选</h2></div>
    <div class="panel-body" id="watchlist" aria-live="polite"></div>
  </div>

  <div class="panel">
    <div class="panel-header">
      <h2>📡 策略监控</h2>
      <span class="badge" id="monitor-status">检查中…</span>
    </div>
    <div class="panel-body" id="monitor-alerts" aria-live="polite">
      <div class="empty">加载中…</div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-header"><h2>操作</h2></div>
    <form id="entry" class="form-grid">
      <div class="form-group full">
        <label for="action">action</label>
        <select id="action">
          <option value="add_position">add_position · 加仓/建仓</option>
          <option value="reduce_position">reduce_position · 减仓</option>
          <option value="remove_position">remove_position · 清仓</option>
          <option value="update_position">update_position · 修改字段</option>
          <option value="tag_position">tag_position · 追加标签</option>
          <option value="untag_position">untag_position · 删除标签</option>
          <option value="add_watch">add_watch · 加自选</option>
          <option value="update_watch">update_watch · 改自选</option>
          <option value="remove_watch">remove_watch · 删自选</option>
        </select>
      </div>
      <div class="form-group">
        <label for="code">code</label>
        <input id="code" list="codes" autocomplete="off" autocapitalize="off" autocorrect="off"
               placeholder="sh600989" required>
        <datalist id="codes">__DATALIST__</datalist>
      </div>
      <div class="form-group" data-show="add_position">
        <label for="name">name <span style="color:var(--text-muted)">(可选)</span></label>
        <input id="name" placeholder="宝丰能源">
      </div>
      <div class="form-group" data-show="add_position update_position update_watch">
        <label for="cost">cost <span class="required" data-required="add_position">*</span></label>
        <input id="cost" type="number" step="0.001" placeholder="18.500">
      </div>
      <div class="form-group" data-show="add_position reduce_position update_position">
        <label for="quantity">quantity <span class="required" data-required="add_position reduce_position">*</span></label>
        <input id="quantity" type="number" step="1" placeholder="1000">
      </div>
      <div class="form-group" data-show="add_position">
        <label for="buy_date">buy_date</label>
        <input id="buy_date" type="date">
      </div>
      <div class="form-group" data-show="add_position tag_position untag_position update_position">
        <label for="tags">tags <span class="warn" data-warn="update_position">⚠ 整列表替换</span></label>
        <input id="tags" placeholder="长线, 能源">
      </div>
      <div class="form-group" data-show="add_watch update_watch">
        <label for="name_w">name <span style="color:var(--text-muted)">(可选)</span></label>
        <input id="name_w" placeholder="华友钴业">
      </div>
      <div class="form-group" data-show="add_watch update_watch">
        <label for="target_buy">target_buy</label>
        <input id="target_buy" type="number" step="0.01" placeholder="28.00">
      </div>
      <div class="form-group" data-show="add_watch update_watch">
        <label for="target_sell">target_sell</label>
        <input id="target_sell" type="number" step="0.01" placeholder="42.00">
      </div>
      <div class="form-group full" data-show="remove_position reduce_position" id="confirm-wrap" style="display:none">
        <div class="destructive">⚠ 确认执行此不可逆操作</div>
      </div>
      <div class="form-group full">
        <button type="submit" class="btn-submit" id="submit-btn">提交</button>
      </div>
    </form>
  </div>

  <div class="panel">
    <div class="panel-header">
      <h2>Webhook</h2>
      <button class="btn-copy" id="copy" aria-label="复制 cURL">copy</button>
    </div>
    <pre id="curl"><span class="kw">curl</span> -X POST http://127.0.0.1:8765/api/positions \\
  -H <span class="str">'Content-Type: application/json'</span> \\
  -H <span class="str">'Authorization: Bearer &lt;YOUR_TOKEN&gt;'</span> \\
  -d <span class="str">'{"action":"add_position","code":"sh600989","cost":18.5,"quantity":1000,"tags":["长线"]}'</span></pre>
  </div>

</div>

<script>
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
let toastTimer;
const TOKEN = new URLSearchParams(location.search).get("token") || "";
const AUTH = TOKEN ? {"Authorization": "Bearer " + TOKEN} : {};

function showToast(msg, ok) {
  const t = $("#toast");
  t.className = "toast " + (ok ? "ok" : "err");
  t.textContent = msg;
  t.offsetHeight;
  t.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("visible"), ok ? 3000 : 6000);
}

const WARN_MAP = {
  update_position_replaces_tags: "tags 字段已整体替换（非合并）",
  position_removed: "持仓已全部卖出并清除",
};

function syncFields() {
  const a = $("#action").value;
  $$("[data-show]").forEach(el => {
    const vis = el.dataset.show.split(" ").includes(a);
    el.style.display = vis ? "" : "none";
    if (!vis) el.querySelectorAll("input,select").forEach(i => { if (i.id !== "code") i.value = ""; });
  });
  $$("[data-required]").forEach(el => {
    el.style.display = el.dataset.required.split(" ").includes(a) ? "" : "none";
  });
  $$("[data-warn]").forEach(el => {
    el.style.display = el.dataset.warn === a ? "" : "none";
  });
  const cw = $("#confirm-wrap");
  if (cw) cw.style.display = (a === "remove_position" || a === "reduce_position") ? "" : "none";
}

async function loadList() {
  try {
    const r = await fetch("/api/positions", {headers: AUTH});
    const j = await r.json();
    if (!j.ok) throw new Error(j.error);
    renderPositions(j.data.positions);
    renderWatch(j.data.watchlist);
  } catch (e) {
    showToast("加载失败: " + e.message, false);
  }
}

function renderPositions(rows) {
  const el = $("#positions");
  if (!rows.length) { el.innerHTML = '<div class="empty">暂无持仓</div>'; return; }
  let h = '<table><tr><th>代码</th><th>名称</th><th>成本</th><th>数量</th><th>买入日</th><th>标签</th></tr>';
  for (const p of rows) {
    const tags = (p.tags||[]).map(t => '<span class="code-tag">'+t+'</span>').join("");
    h += '<tr><td>'+p.code+'</td><td>'+(p.name||"—")+'</td><td>'+p.cost+'</td><td>'+p.quantity+'</td><td>'+(p.buy_date||"—")+'</td><td>'+(tags||"—")+'</td></tr>';
  }
  el.innerHTML = h + "</table>";
}

function renderWatch(rows) {
  const el = $("#watchlist");
  if (!rows.length) { el.innerHTML = '<div class="empty">暂无自选</div>'; return; }
  let h = '<table><tr><th>代码</th><th>名称</th><th>目标买</th><th>目标卖</th><th>加入日</th></tr>';
  for (const w of rows) {
    h += '<tr><td>'+w.code+'</td><td>'+(w.name||"—")+'</td><td>'+(w.target_buy||"—")+'</td><td>'+(w.target_sell||"—")+'</td><td>'+(w.added_date||"—")+'</td></tr>';
  }
  el.innerHTML = h + "</table>";
}

function resetForm() {
  ["#name","#name_w","#cost","#quantity","#buy_date","#tags","#target_buy","#target_sell"].forEach(id => {
    const el = $(id); if (el) el.value = "";
  });
}

$("#action").addEventListener("change", syncFields);
syncFields();

$("#entry").addEventListener("submit", async (e) => {
  e.preventDefault();
  const a = $("#action").value;
  const code = $("#code").value.trim();
  if (!code) { showToast("请填写代码", false); return; }

  if (a === "remove_position" && !confirm("确认清仓 " + code + "？此操作不可撤销。")) return;
  if (a === "reduce_position") {
    const q = parseInt($("#quantity").value);
    if (!q || q <= 0) { showToast("请输入有效的减仓数量", false); return; }
    if (!confirm("确认减仓 " + code + " " + q + " 股？")) return;
  }

  const body = { action: a, code };
  const set = (id, key) => { const v = $(id).value.trim(); if (v !== "") body[key] = isNaN(+v) ? v : +v; };

  if (a === "add_position") {
    const cost = parseFloat($("#cost").value), qty = parseInt($("#quantity").value);
    if (!cost && cost !== 0) { showToast("成本为必填项", false); return; }
    if (!qty || qty <= 0) { showToast("数量须 > 0", false); return; }
    if ($("#name").value) body.name = $("#name").value;
    body.cost = cost; body.quantity = qty;
    if ($("#buy_date").value) body.buy_date = $("#buy_date").value;
    if ($("#tags").value) body.tags = $("#tags").value.split(",").map(s=>s.trim()).filter(Boolean);
  } else if (a === "reduce_position") {
    set("#quantity", "quantity");
  } else if (a === "update_position") {
    if ($("#cost").value) body.cost = +$("#cost").value;
    if ($("#quantity").value) body.quantity = +$("#quantity").value;
    if ($("#tags").value) body.tags = $("#tags").value.split(",").map(s=>s.trim()).filter(Boolean);
  } else if (a === "tag_position" || a === "untag_position") {
    body.tags = $("#tags").value.split(",").map(s=>s.trim()).filter(Boolean);
    if (!body.tags.length) { showToast("请填写至少一个标签", false); return; }
  } else if (a === "add_watch" || a === "update_watch") {
    if ($("#name_w").value) body.name = $("#name_w").value;
    if ($("#target_buy").value) body.target_buy = +$("#target_buy").value;
    if ($("#target_sell").value) body.target_sell = +$("#target_sell").value;
  }

  const btn = $("#submit-btn");
  btn.disabled = true; btn.textContent = "提交中…";
  try {
    const r = await fetch("/api/positions", {
      method: "POST", headers: { "Content-Type": "application/json", ...AUTH },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!j.ok) { showToast(j.error + (j.detail ? ": " + j.detail : ""), false); return; }
    let msg = "✓ 成功";
    if (j.warn && j.warn.length) msg += " · " + j.warn.map(w => WARN_MAP[w]||w).join("；");
    showToast(msg, true);
    resetForm();
    await loadList();
  } catch (e) {
    showToast("请求失败: " + e.message, false);
  } finally {
    btn.disabled = false; btn.textContent = "提交";
  }
});

$("#refresh").addEventListener("click", () => { loadList(); loadMonitor(); });
$("#copy").addEventListener("click", async () => {
  const raw = $("#curl").textContent;
  try { await navigator.clipboard.writeText(raw); showToast("已复制", true); }
  catch { showToast("复制失败", false); }
});

loadList();

async function loadMonitor() {
  try {
    const r = await fetch("/api/monitor", {headers: AUTH});
    const j = await r.json();
    if (!j.ok) return;
    const d = j.data;
    const statusEl = $("#monitor-status");
    const alertsEl = $("#monitor-alerts");
    if (d.enabled) {
      statusEl.textContent = d.trading_hours ? "🟢 盘中监控中" : "⏸ 非交易时段";
      statusEl.style.color = d.trading_hours ? "var(--success)" : "var(--text-muted)";
    } else {
      statusEl.textContent = "❌ 已禁用";
      statusEl.style.color = "var(--error)";
    }
    const lr = d.last_result;
    if (!lr || !lr.details || !lr.details.length) {
      alertsEl.innerHTML = '<div class="empty">暂无预警（等待首次扫描…）</div>';
      return;
    }
    let h = '<table><tr><th>标的</th><th>类型</th><th>预警</th><th>价格</th><th>状态</th></tr>';
    const typeMap = {support_touch:"支撑触及",resistance_touch:"压力触及",target_buy:"到目标买",target_sell:"到目标卖",macd_golden:"MACD金叉",macd_dead:"MACD死叉",ma_break:"均线突破",near_limit:"涨跌停近",stop_loss:"止损",take_profit:"止盈"};
    for (const a of lr.details) {
      const icon = a.pushed ? "✅" : "⏭️";
      h += '<tr><td><span class="code-tag">'+a.code+'</span> '+(a.name||"")+'</td><td>'+(typeMap[a.type]||a.type)+'</td><td>'+a.message+'</td><td>'+a.price+'</td><td>'+icon+'</td></tr>';
    }
    h += '</table>';
    h += '<div style="padding:8px 14px;font-size:12px;color:var(--text-muted)">扫描: '+lr.scanned+' | 预警: '+lr.alerts+' | 推送: '+lr.pushed+' · '+lr.timestamp+'</div>';
    alertsEl.innerHTML = h;
  } catch (e) {
    // 静默失败
  }
}
loadMonitor();
</script>
</body>
</html>
"""


# ===== Server 工厂 =====
def make_server(host: str, port: int, data_file: Optional[str] = None) -> ThreadingHTTPServer:
    """构造 ThreadingHTTPServer 实例（不启动），供 __main__ 与测试共用。"""
    global _data_file
    _data_file = data_file
    # 测试场景下允许先 reset 单例，使新 data_file 生效
    _reset_pm_for_tests()
    # 允许端口 TIME_WAIT 期间快速重启（smoke / dev 重启友好）
    ThreadingHTTPServer.allow_reuse_address = True
    return ThreadingHTTPServer((host, port), Handler)


# ===== 入口 =====
def main():
    parser = argparse.ArgumentParser(
        description="持仓录入 Web 服务（仅本机，零依赖 stdlib http.server）",
    )
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8765, help="监听端口（默认 8765）")
    parser.add_argument("--data-file", default=None,
                        help="portfolio.json 路径（默认 scripts/data/portfolio.json）")
    parser.add_argument("--no-open", action="store_true", default=False,
                        help="启动后不自动打开浏览器（默认自动打开）")
    parser.add_argument("--notify", action="store_true", default=True,
                        help="启用持仓变更推送（默认开启，自动读取 notification.yaml）")
    parser.add_argument("--no-notify", dest="notify", action="store_false",
                        help="禁用持仓变更推送")
    parser.add_argument("--monitor", action="store_true", default=True,
                        help="启用后台监控（默认开启）")
    parser.add_argument("--no-monitor", dest="monitor", action="store_false",
                        help="禁用后台监控")
    parser.add_argument("--monitor-interval", type=int, default=300,
                        help="监控检查间隔秒数（默认 300）")
    parser.add_argument("--allow-public-bind", action="store_true",
                        help="允许绑定到 0.0.0.0（默认拒绝）")
    args = parser.parse_args()

    if args.host == "0.0.0.0" and not args.allow_public_bind:
        print("ERROR: 绑定 0.0.0.0 需显式 --allow-public-bind 参数", file=sys.stderr)
        sys.exit(1)

    # 跳过预检直接启动——ThreadingHTTPServer.allow_reuse_address 已为 True，
    # 可接管 TIME_WAIT；预检 socket 未设 SO_REUSEADDR 反而会留下 TIME_WAIT 导致 bind 失败。
    try:
        server = make_server(args.host, args.port, args.data_file)
    except OSError as e:
        print(f"ERROR: 无法启动 ({args.host}:{args.port}): {e}", file=sys.stderr)
        print(f"提示: 用 `lsof -i:{args.port}` 查看占用进程", file=sys.stderr)
        sys.exit(1)

    bound_host, bound_port = server.server_address
    token = _ensure_token()
    print(f"Portfolio Web 启动: http://{bound_host}:{bound_port}/?token={token}", flush=True)
    print(f"  Token: {token}", flush=True)
    print(f"  数据文件: {args.data_file or _SCRIPTS_DIR / 'data' / 'portfolio.json'}", flush=True)

    # 自动打开浏览器（默认行为，--no-open 可禁用）
    if not args.no_open:
        import webbrowser
        url = f"http://{bound_host}:{bound_port}/?token={token}"
        try:
            webbrowser.open(url)
            print(f"  浏览器已打开: {url}", flush=True)
        except Exception:
            print(f"  浏览器打开失败，请手动访问: {url}", flush=True)

    # 通知推送
    global _notify_enabled
    if args.notify:
        _notify_enabled = True
        nm = _get_notifier()
        if nm:
            channels = nm.get_active_channels()
            print(f"  通知推送: ✅ 已接入 ({', '.join(channels)})", flush=True)
        else:
            print(f"  通知推送: ⚠ 未配置通道（编辑 scripts/config/notification.yaml 开启）", flush=True)
    else:
        print(f"  通知推送: ❌ 已禁用", flush=True)

    # 后台监控
    global _monitor_enabled, _monitor_thread, _monitor_interval
    if args.monitor:
        _monitor_enabled = True
        _monitor_interval = args.monitor_interval
        _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
        _monitor_thread.start()
    else:
        print(f"  后台监控: ❌ 已禁用", flush=True)

    print(f"  停止: Ctrl-C", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down…", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
