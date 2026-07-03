"""事件日历数据获取入口。

用法:
    from data.event import get_events

    events = get_events("sh600519", days=30)

内部遍历 5 个 event fetcher（earnings/lockup/dividend/shareholder/violation），
按子类型聚合返回。不走 DataFetcherManager——event 域的 5 个 fetcher 返回的是
不同类型的数据，不是同数据多源故障转移场景。
"""

import threading
import logging

from common import fetch_with_breaker

logger = logging.getLogger(__name__)

_fetchers_cache: list | None = None
_fetchers_lock = threading.Lock()


def _get_event_fetchers():
    """延迟导入并缓存 event fetcher 列表。"""
    global _fetchers_cache
    if _fetchers_cache is not None:
        return _fetchers_cache
    with _fetchers_lock:
        if _fetchers_cache is not None:
            return _fetchers_cache
        from fetchers import get_event_fetchers

        _fetchers_cache = get_event_fetchers()
    return _fetchers_cache


def get_events(code: str, days: int = 30) -> dict:
    """获取指定股票的近期事件。

    Args:
        code: 股票代码（如 sh600519）
        days: 查询天数（默认 30）

    Returns:
        {"code":..., "query_days":..., "earnings":[], "lockup":[],
         "dividend":[], "shareholder":[], "violation":[], "summary": str}
    """
    result = {
        "code": code,
        "query_days": days,
        "earnings": [],
        "lockup": [],
        "dividend": [],
        "shareholder": [],
        "violation": [],
    }

    fetchers = _get_event_fetchers()
    # 全部 fetcher 都接受 **kwargs，calendar 类用 days，个股类忽略
    for fetcher in fetchers:
        try:
            data = fetch_with_breaker(fetcher, code, days=days)
            if data and data.get("items"):
                result[data["type"]] = data["items"]
        except Exception as e:
            logger.debug(
                "事件 fetcher %s 失败 %s: %s",
                fetcher.__class__.__name__,
                code,
                e,
            )

    # 生成摘要
    summary_parts = []
    if result["earnings"]:
        nearest = result["earnings"][0]
        summary_parts.append(f"📊 财报披露: {nearest.get('disclosure_date', '?')}")
    if result["lockup"]:
        nearest = result["lockup"][0]
        summary_parts.append(f"🔓 解禁: {nearest.get('free_date', '?')}")
    if result["dividend"]:
        nearest = result["dividend"][0]
        summary_parts.append(f"💰 分红: {nearest.get('ex_date', '?')}")
    if result["shareholder"]:
        nearest = result["shareholder"][0]
        direction = "增持" if nearest.get("direction") == "increase" else "减持"
        summary_parts.append(f"👤 大股东{direction}: {nearest.get('end_date', '?')}")
    if result["violation"]:
        nearest = result["violation"][0]
        summary_parts.append(f"⚠️ 违规: {nearest.get('punish_date', '?')}")

    if summary_parts:
        result["summary"] = " | ".join(summary_parts)
    else:
        result["summary"] = f"近 {days} 日无重大事件"

    return result
