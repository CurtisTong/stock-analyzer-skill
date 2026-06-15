"""
工具函数模块。

提供认证、通知、数据解析等工具函数。
"""
import json
import os
import secrets
import stat
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# 模块级状态
_pm = None
_lock = threading.RLock()
_server_start = time.time()
_data_file = None
_log_lock = threading.Lock()
_notify_enabled = False
_nm = None
_monitor_enabled = False
_monitor_thread = None
_monitor_stop_event = threading.Event()
_monitor_interval = 300
_monitor_last_result = None
_token = None
_virtual_mode = False

# Bearer Token 认证
_TOKEN_DIR = Path.home() / ".config" / "stock-analyzer"
_TOKEN_FILE = _TOKEN_DIR / "portfolio_web.token"

# 防御性常量
MAX_BODY_BYTES = 8 * 1024


def _ensure_token() -> str:
    """读取或生成 Bearer token。"""
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


def _err(msg: str, code: int = 400, detail: str = "") -> dict:
    """生成错误响应。"""
    return {"ok": False, "error": msg, "code": code, "detail": detail}


def _ok(data: Any, warn: Optional[list] = None) -> dict:
    """生成成功响应。"""
    payload = {"ok": True, "data": data}
    if warn:
        payload["warn"] = warn
    return payload


def _get_pm(virtual: Optional[bool] = None):
    """获取 PortfolioManager 单例。"""
    global _pm
    if virtual is None:
        virtual = _virtual_mode
    with _lock:
        if _pm is None or _pm.is_virtual != virtual:
            from portfolio import PortfolioManager
            _pm = PortfolioManager(path=_data_file, virtual=virtual)
        return _pm


def _reset_pm_for_tests() -> None:
    """测试用：清空单例。"""
    global _pm
    with _lock:
        _pm = None


def _parse_float(v: Any) -> Optional[float]:
    """解析浮点数。"""
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_int(v: Any) -> Optional[int]:
    """解析整数。"""
    if v is None or isinstance(v, bool):
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
    """根据 action 和结果格式化通知标题和内容。"""
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
    """扫 portfolio.json + portfolio_example.json + sector_stocks.json。"""
    scripts_data = Path(__file__).parent.parent.parent / "data"
    seen = {}

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


def _is_trading_hours() -> bool:
    """检查当前是否在交易时段。"""
    from data.config import is_trading_hours as _official_is_trading_hours
    return _official_is_trading_hours()


def _monitor_loop():
    """后台监控线程。"""
    global _monitor_last_result
    import importlib
    try:
        alert_engine = importlib.import_module("monitor.alert_engine")
    except ImportError:
        print("  ⚠ 监控模块加载失败（monitor.alert_engine）", flush=True)
        return

    print(f"  📡 后台监控已启动（每 {_monitor_interval} 秒检查一次）", flush=True)

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
        except Exception as e:
            print(f"  ⚠ 监控异常: {e}", flush=True)

        _monitor_stop_event.wait(timeout=_monitor_interval)

    print("  📡 后台监控已停止", flush=True)
