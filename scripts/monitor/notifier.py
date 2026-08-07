"""盘中检查与推送。

从 alert_engine.py 拆分，负责扫描全部标的、过滤预警级别、构造推送内容并调用 NotificationManager。
scan_all 原位于 scanner.py，该文件在 758b1c2 被删除后无替代实现，此处内联恢复。
"""

import logging
import threading
from datetime import datetime

from common import to_float
from monitor.rules import ALERT_LEVELS, _LEVEL_META, get_alert_level
from monitor.levels import compute_key_levels

logger = logging.getLogger(__name__)

# P2-H5: 持续性信号（MACD 金叉/死叉、均线突破等）edge-triggered 状态记录。
# 同一标的同一信号类型当日只推送一次，避免调度间隔 > 去重窗口时重复推送。
# key: f"{code}:{alert_type}", value: (日期字符串, 记录时间戳)
_NOTIFIED_MAX_SIZE = 10000  # 最大容量限制
_NOTIFIED_TTL_SECONDS = 86400  # 24h 过期清理

_notified_signals: dict = {}
_notified_lock = threading.Lock()


# ── 持仓+自选股扫描（原 scanner.py，758b1c2 删除后内联恢复） ──

_pm = None
_pm_singleton_lock = threading.Lock()


def _get_pm():
    """获取 PortfolioManager 单例（线程安全）。"""
    global _pm
    if _pm is None:
        with _pm_singleton_lock:
            if _pm is None:
                from portfolio import PortfolioManager

                _pm = PortfolioManager()
    return _pm


def scan_all(pm=None) -> list:
    """扫描持仓+自选股，返回关键点位集合。

    Args:
        pm: 可选的 PortfolioManager 实例（依赖注入）。None 时使用本模块
            的 _get_pm() 单例，保持向后兼容。调用方若已有 portfolio/web/utils.py
            的 _get_pm() 单例，应显式传入以避免双单例问题。
    """
    if pm is None:
        pm = _get_pm()
    positions = pm.get_positions()
    watchlist = pm.get_watchlist()

    # 批量预获取行情（减少串行 HTTP 请求）
    all_codes = [p.get("code", "") for p in positions if p.get("code")]
    pos_codes = set(all_codes)
    for w in watchlist:
        code = w.get("code", "")
        if code and code not in pos_codes:
            all_codes.append(code)

    if all_codes:
        try:
            from data import get_quotes

            get_quotes(all_codes, use_cache=True)
        except Exception as e:
            logger.debug("批量预获取行情失败，将逐股获取: %s", e)

    results = []

    # 持仓
    for pos in positions:
        code = pos.get("code", "")
        if not code:
            continue
        r = compute_key_levels(code, position=pos)
        results.append(r)

    # 自选（去重）
    for w in watchlist:
        code = w.get("code", "")
        if not code or code in pos_codes:
            continue
        r = compute_key_levels(code, watch=w)
        results.append(r)

    return results


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
                k
                for k, v in _notified_signals.items()
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

            # P2-H5: 持续性信号当日只推送一次，
            # 避免调度间隔 > 去重窗口（15min）时重复推送（edge-triggered）。
            # gain_reduce 不在此列：涨幅台阶变化时应重新推送，靠 throttle 15min 去重即可。
            # vwap_deviation 不在此列：偏离是持续状态，靠 throttle 限频。
            _PERSISTENT_SIGNALS = {
                "macd_golden",
                "macd_dead",
                "ma_break",
                "ma_stop_loss",
                "vwap_cross_up",
                "vwap_cross_down",
            }
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
