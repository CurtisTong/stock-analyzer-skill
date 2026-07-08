"""盘中检查与推送。

从 alert_engine.py 拆分，负责扫描全部标的、过滤预警级别、构造推送内容并调用 NotificationManager。
"""

import logging
import threading
from datetime import datetime

from common import to_float
from monitor.rules import ALERT_LEVELS, _LEVEL_META, get_alert_level
from monitor.scanner import scan_all

logger = logging.getLogger(__name__)

# P2-H5: 持续性信号（MACD 金叉/死叉、均线突破等）edge-triggered 状态记录。
# 同一标的同一信号类型当日只推送一次，避免调度间隔 > 去重窗口时重复推送。
# key: f"{code}:{alert_type}", value: (日期字符串, 记录时间戳)
_NOTIFIED_MAX_SIZE = 10000  # 最大容量限制
_NOTIFIED_TTL_SECONDS = 86400  # 24h 过期清理

_notified_signals: dict = {}
_notified_lock = threading.Lock()


def _should_notify_signal(code: str, alert_type: str) -> bool:
    """持续性信号当日是否首次触发（edge-triggered），同时清理过期条目。"""
    import time

    now = time.time()
    today = datetime.now().strftime("%Y-%m-%d")
    key = f"{code}:{alert_type}"
    with _notified_lock:
        # P0-21: 硬上限 LRU 强制淘汰最旧条目
        if len(_notified_signals) >= _NOTIFIED_MAX_SIZE:
            # 按时间戳升序排序，淘汰最早的 10%
            sorted_keys = sorted(
                _notified_signals.items(),
                key=lambda kv: kv[1][1] if isinstance(kv[1], tuple) else 0,
            )
            evict_count = max(1, _NOTIFIED_MAX_SIZE // 10)
            for k, _ in sorted_keys[:evict_count]:
                _notified_signals.pop(k, None)
        # 容量 + TTL 过期清理
        if len(_notified_signals) > _NOTIFIED_MAX_SIZE // 2:
            expired = [
                k for k, v in _notified_signals.items()
                if isinstance(v, tuple) and now - v[1] > _NOTIFIED_TTL_SECONDS
            ]
            for k in expired:
                del _notified_signals[k]
        last = _notified_signals.get(key)
        if isinstance(last, tuple):
            if last[0] == today:
                return False
        elif isinstance(last, str):
            # 向后兼容旧格式（纯日期字符串）
            if last == today:
                return False
        _notified_signals[key] = (today, now)
    return True

# 模块级缓存（惰性初始化）
_nm = None
_singleton_lock = threading.Lock()


def _get_nm():
    """获取 NotificationManager 单例（线程安全）。"""
    global _nm
    if _nm is None:
        with _singleton_lock:
            if _nm is None:
                from monitor import NotificationManager

                _nm = NotificationManager()
    return _nm


def _reset_cache():
    """重置缓存（用于测试）。"""
    global _nm
    _nm = None


def check_and_push(dry_run: bool = False, level: str = "important") -> dict:
    """盘中检查：扫描全部标的，触发预警则推送。

    Args:
        dry_run: 只输出不推送
        level: 推送级别阈值（"urgent"/"important"/"normal"）

    Returns:
        {"scanned": int, "alerts": int, "pushed": int, "details": [...]}
    """
    results = scan_all()
    nm = _get_nm() if not dry_run else None

    # 级别阈值：只推送 >= level 的预警
    level_order = {"normal": 0, "important": 1, "urgent": 2}
    min_level = level_order.get(level, 1)

    summary = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "scanned": len(results),
        "alerts": 0,
        "filtered": 0,
        "pushed": 0,
        "level": level,
        "details": [],
    }

    for r in results:
        code = r["code"]
        name = r.get("name", code)
        price = r.get("price", 0)
        alerts = r.get("alerts", [])

        if not alerts:
            continue

        summary["alerts"] += len(alerts)

        for alert in alerts:
            alert_type = alert.get("type", "unknown")
            message = alert.get("message", "")
            urgent = alert.get("urgent", False)

            # 计算预警级别
            alert_level = get_alert_level(alert_type, urgent)
            alert_level_value = level_order.get(alert_level, 0)

            # 过滤低级别预警
            if alert_level_value < min_level:
                summary["filtered"] += 1
                continue

            # 构造推送内容
            level_icon = {"urgent": "🔴", "important": "🟡", "normal": "🟢"}.get(
                alert_level, "⚪"
            )
            body = f"{level_icon} [{_LEVEL_META[alert_level]['name']}]"
            body += f"\n现价 {price}"
            if r.get("change_pct"):
                body += f"（{r['change_pct']:+.2f}%）"
            body += f"\n{message}"

            # 持仓信息
            if r.get("position"):
                pos = r["position"]
                cost = to_float(pos.get("cost", 0))
                qty = to_float(pos.get("quantity", 0))
                if cost > 0 and qty > 0:
                    pnl = (price - cost) * qty
                    pnl_pct = (price - cost) / cost * 100
                    body += f"\n持仓 {int(qty)} 股 | 盈亏 {pnl:+,.0f}({pnl_pct:+.1f}%)"

            detail = {
                "code": code,
                "name": name,
                "type": alert_type,
                "level": alert_level,
                "message": message,
                "price": price,
                "pushed": False,
            }

            # P2-H5: 持续性信号（MACD 金叉/死叉、均线突破）当日只推送一次，
            # 避免调度间隔 > 去重窗口（15min）时重复推送（edge-triggered）。
            _PERSISTENT_SIGNALS = {"macd_golden", "macd_dead", "ma_break"}
            if alert_type in _PERSISTENT_SIGNALS and not _should_notify_signal(
                code, alert_type
            ):
                summary["filtered"] += 1
                summary["details"].append(detail)
                continue

            if not dry_run and nm:
                push_type = ALERT_LEVELS.get(alert_type, {}).get("push_type", "price")
                result = nm.send_alert(
                    alert_type=push_type,
                    stock_name=name,
                    stock_code=code,
                    message=body,
                    urgent=urgent,
                )
                detail["pushed"] = result.get("sent", 0) > 0
                if detail["pushed"]:
                    summary["pushed"] += 1
                elif alert_type in _PERSISTENT_SIGNALS:
                    # 推送失败：清除去重记录，下次重试
                    key = f"{code}:{alert_type}"
                    with _notified_lock:
                        _notified_signals.pop(key, None)

            summary["details"].append(detail)

    return summary
