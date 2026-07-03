"""资金流向数据获取入口。

用法:
    from data.flow import get_northbound_flow, get_stock_flow

    nb = get_northbound_flow(code, days=20)
    sf = get_stock_flow("sh600519", days=10)

内部走 fetchers.get_flow_fetchers() 拿 fetcher 列表。
flow 域的 2 个 fetcher 返回不同类型数据（北向资金/个股资金），不走 manager 故障转移。
"""

import threading
import logging

from common import fetch_with_breaker

logger = logging.getLogger(__name__)

_fetchers_cache: list | None = None
_fetchers_lock = threading.Lock()


def _get_flow_fetchers():
    """延迟导入并缓存 flow fetcher 列表。"""
    global _fetchers_cache
    if _fetchers_cache is not None:
        return _fetchers_cache
    with _fetchers_lock:
        if _fetchers_cache is not None:
            return _fetchers_cache
        from fetchers import get_flow_fetchers

        _fetchers_cache = get_flow_fetchers()
    return _fetchers_cache


def _find_fetcher(name_prefix: str):
    """按 name 前缀查找 fetcher。"""
    for f in _get_flow_fetchers():
        if f.name.startswith(name_prefix):
            return f
    return None


def get_northbound_flow(code: str, days: int = 20) -> list:
    """获取北向资金近期数据。

    Args:
        code: 股票代码（北向资金是市场整体数据，code 参数实际忽略）
        days: 获取天数（默认 20）

    Returns:
        按日期升序排列的列表，元素形如
        {"date":..., "net_buy": float, "sh_net":..., "sz_net":...}
        失败返回空列表。

    注意：返回值用 net_buy 字段（= total_net），与 strategies/factors/chip.py
    的 _score_northbound_flow 期望的字段名对齐。
    """
    fetcher = _find_fetcher("northbound")
    if fetcher is None:
        return []
    try:
        result = fetch_with_breaker(fetcher, code, days=days)
    except Exception as e:
        logger.debug("北向资金 fetch 失败 %s: %s", code, e)
        return []
    if not result or "days" not in result:
        return []
    # 映射 total_net -> net_buy，保持调用方期望的字段名
    return [
        {
            "date": d.get("date", ""),
            "net_buy": d.get("total_net", 0),
            "sh_net": d.get("sh_net", 0),
            "sz_net": d.get("sz_net", 0),
        }
        for d in result["days"]
    ]


def get_stock_flow(code: str, days: int = 10) -> dict | None:
    """获取个股资金流向。

    Args:
        code: 股票代码
        days: 获取天数（默认 10）

    Returns:
        fetcher 原始返回的 dict（含 type/days 字段），失败返回 None。
    """
    fetcher = _find_fetcher("stock_flow")
    if fetcher is None:
        return None
    try:
        return fetch_with_breaker(fetcher, code, days=days)
    except Exception as e:
        logger.debug("个股资金流向 fetch 失败 %s: %s", code, e)
        return None
