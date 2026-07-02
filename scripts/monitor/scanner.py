"""持仓+自选股扫描。

从 alert_engine.py 拆分，负责批量扫描持仓和自选股的关键点位。
"""

import logging
import threading

from data import get_quotes
from monitor.levels import compute_key_levels

logger = logging.getLogger(__name__)

# 模块级缓存（惰性初始化）
_pm = None
_singleton_lock = threading.Lock()


def _get_pm():
    """获取 PortfolioManager 单例（线程安全）。"""
    global _pm
    if _pm is None:
        with _singleton_lock:
            if _pm is None:
                from portfolio import PortfolioManager

                _pm = PortfolioManager()
    return _pm


def scan_all() -> list:
    """扫描持仓+自选股，返回关键点位集合。"""
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
