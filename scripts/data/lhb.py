"""龙虎榜数据获取入口。

用法:
    from data.lhb import get_lhb_detail, get_lhb_seats

    detail = get_lhb_detail(code="", days=7)
    seats = get_lhb_seats("sh600519")

内部走 fetchers.get_lhb_fetchers() 拿 fetcher 列表。
lhb 域的 2 个 fetcher 返回不同类型数据（明细/席位），不走 manager 故障转移。
"""

import threading
import logging
from typing import List

logger = logging.getLogger(__name__)

_fetchers_cache: list | None = None
_fetchers_lock = threading.Lock()


def _get_lhb_fetchers():
    """延迟导入并缓存 lhb fetcher 列表。"""
    global _fetchers_cache
    if _fetchers_cache is not None:
        return _fetchers_cache
    with _fetchers_lock:
        if _fetchers_cache is not None:
            return _fetchers_cache
        from fetchers import get_lhb_fetchers

        _fetchers_cache = get_lhb_fetchers()
    return _fetchers_cache


def _find_fetcher(name_prefix: str):
    """按 name 前缀查找 fetcher。"""
    for f in _get_lhb_fetchers():
        if f.name.startswith(name_prefix):
            return f
    return None


def get_lhb_detail(code: str = "", days: int = 7) -> dict | None:
    """获取龙虎榜明细。

    Args:
        code: 股票代码（空值返回近期全部龙虎榜）
        days: 查询天数（默认 7）

    Returns:
        {"type":"lhb_detail", "items":[...]}，失败返回 None。
    """
    fetcher = _find_fetcher("lhb_detail")
    if fetcher is None:
        return None
    try:
        return fetcher.fetch(code, days=days)
    except Exception as e:
        logger.debug("龙虎榜明细 fetch 失败 %s: %s", code, e)
        return None


def get_lhb_seats(code: str, date: str = "") -> dict | None:
    """获取指定股票的龙虎榜买卖席位。

    Args:
        code: 股票代码
        date: 交易日期（空值取最新）

    Returns:
        {"type":"lhb_seat", "items":[...]}，失败返回 None。
    """
    fetcher = _find_fetcher("lhb_seat")
    if fetcher is None:
        return None
    try:
        return fetcher.fetch(code, date=date)
    except Exception as e:
        logger.debug("龙虎榜席位 fetch 失败 %s: %s", code, e)
        return None
