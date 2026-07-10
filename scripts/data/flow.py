"""资金流向数据获取入口。

用法:
    from data.flow import get_northbound_flow, get_stock_flow

    nb = get_northbound_flow(code, days=20)
    sf = get_stock_flow("sh600519", days=10)

内部走 fetchers.get_flow_fetchers() 拿 fetcher 列表。
flow 域的 2 个 fetcher 返回不同类型数据（北向资金/个股资金），不走 manager 故障转移。
"""

import logging

from common import fetch_with_breaker, fetch_with_fallback, LazyFetcherRegistry

logger = logging.getLogger(__name__)


def _get_flow_fetchers_import():
    """fetcher 导入工厂函数。"""
    from fetchers import get_flow_fetchers

    return get_flow_fetchers()


_registry = LazyFetcherRegistry(_get_flow_fetchers_import)


def get_northbound_flow(code: str, days: int = 20) -> list:
    """获取北向资金近期数据。

    v2.4.0: 支持多源故障转移（eastmoney → sina 备份）
    优先使用 eastmoney 的明细（沪/深股通分离），失败回退到 sina。

    Args:
        code: 股票代码（北向资金是市场整体数据，code 参数实际忽略）
        days: 获取天数（默认 20）

    Returns:
        按日期升序排列的列表，元素形如
        {"date":..., "net_buy": float, "sh_net":..., "sz_net":...}
        失败返回空列表。
    """
    # v2.4.0: 多源故障转移（T22: 统一用 fetch_with_fallback）
    fetchers = [f for f in _registry.get_all() if f.name.startswith("northbound")]
    for fetcher in fetchers:
        try:
            result = fetch_with_fallback([fetcher], code, days=days)
        except Exception as e:
            logger.debug("北向资金 %s 失败: %s", type(fetcher).__name__, e)
            continue
        if not result or "days" not in result:
            continue
        return [
            {
                "date": d.get("date", ""),
                "net_buy": d.get("total_net", 0),
                "sh_net": d.get("sh_net", 0),
                "sz_net": d.get("sz_net", 0),
            }
            for d in result["days"]
        ]
    return []


def get_stock_flow(code: str, days: int = 10) -> dict | None:
    """获取个股资金流向。

    Args:
        code: 股票代码
        days: 获取天数（默认 10）

    Returns:
        fetcher 原始返回的 dict（含 type/days 字段），失败返回 None。
    """
    fetcher = _registry.find("stock_flow")
    if fetcher is None:
        return None
    try:
        return fetch_with_breaker(fetcher, code, days=days)
    except Exception as e:
        logger.debug("个股资金流向 fetch 失败 %s: %s", code, e)
        return None
