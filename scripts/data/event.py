"""事件日历数据获取入口。

用法:
    from data.event import get_events

    events = get_events("sh600519", days=30)

内部遍历 5 个 event fetcher（earnings/lockup/dividend/shareholder/violation），
按子类型聚合返回。不走 DataFetcherManager——event 域的 5 个 fetcher 返回的是
不同类型的数据，不是同数据多源故障转移场景。
"""

import logging

from common import fetch_with_breaker, LazyFetcherRegistry

logger = logging.getLogger(__name__)


def _get_event_fetchers_import():
    """fetcher 导入工厂函数。"""
    from fetchers import get_event_fetchers

    return get_event_fetchers()


_registry = LazyFetcherRegistry(_get_event_fetchers_import)


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
        "forecast": [],  # (#10) 业绩预告
    }

    fetchers = _registry.get_all()
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
