"""龙虎榜数据获取入口。

用法:
    from data.lhb import get_lhb_detail, get_lhb_seats

    detail = get_lhb_detail(code="", days=7)
    seats = get_lhb_seats("sh600519")

内部走 fetchers.get_lhb_fetchers() 拿 fetcher 列表。
lhb 域的 2 个 fetcher 返回不同类型数据（明细/席位），不走 manager 故障转移。
"""

import logging
import sys
from pathlib import Path

# 直接运行本脚本时补齐 scripts/ 到 import 路径（供 common / fetchers 等同级包）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import fetch_with_breaker, LazyFetcherRegistry

logger = logging.getLogger(__name__)


def _get_lhb_fetchers_import():
    """fetcher 导入工厂函数。"""
    from fetchers import get_lhb_fetchers

    return get_lhb_fetchers()


_registry = LazyFetcherRegistry(_get_lhb_fetchers_import)


def get_lhb_detail(code: str = "", days: int = 7) -> dict | None:
    """获取龙虎榜明细。

    Args:
        code: 股票代码（空值返回近期全部龙虎榜）
        days: 查询天数（默认 7）

    Returns:
        {"type":"lhb_detail", "items":[...]}，失败返回 None。
    """
    fetcher = _registry.find("lhb_detail")
    if fetcher is None:
        return None
    try:
        return fetch_with_breaker(fetcher, code, days=days)
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
    fetcher = _registry.find("lhb_seat")
    if fetcher is None:
        return None
    try:
        return fetch_with_breaker(fetcher, code, date=date)
    except Exception as e:
        logger.debug("龙虎榜席位 fetch 失败 %s: %s", code, e)
        return None
