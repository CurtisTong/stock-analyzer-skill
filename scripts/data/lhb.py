"""龙虎榜数据获取入口。

用法:
    from data.lhb import get_lhb_detail, get_lhb_seats

    detail = get_lhb_detail(code="", days=7)
    seats = get_lhb_seats("sh600519")

内部走 fetchers.get_lhb_fetchers() 拿 fetcher 列表。
lhb 域的 2 个 fetcher 返回不同类型数据（明细/席位），不走 manager 故障转移。
"""

import sys

# 直接运行本脚本时（python3 scripts/data/lhb.py ...），sys.path[0] 是 scripts/data/，
# 其中的 types.py 会遮蔽标准库 types —— Python 3.11+ 在 import logging 阶段就抛
# ImportError: cannot import name 'GenericAlias'。必须在任何标准库导入之前把
# scripts/data 从 sys.path 移走、换成父目录 scripts/；包内 `from data import ...`
# 的绝对导入依赖 scripts/ 在 sys.path，所以只能替换不能清空。
if __name__ == "__main__":
    import os

    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _scripts_root = os.path.dirname(_script_dir)
    sys.path[:] = [_scripts_root] + [p for p in sys.path if p and os.path.abspath(p) != _script_dir]

import logging
from pathlib import Path

from common import fetch_with_breaker, LazyFetcherRegistry
from common.exceptions.silent_fallback import log_silent_fallback

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
        log_silent_fallback("lhb.get_lhb_detail", e)
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
        log_silent_fallback("lhb.get_lhb_seats", e)
        logger.debug("龙虎榜席位 fetch 失败 %s: %s", code, e)
        return None


def main():
    """CLI 入口：查询龙虎榜明细（SKILL.md 声明的命令）。

    用法:
        python3 scripts/data/lhb.py sh600519          # 默认近 7 日
        python3 scripts/data/lhb.py sh600519 --days 10
        python3 scripts/data/lhb.py sh600519 -j       # JSON 输出
    """
    import argparse
    import json

    parser = argparse.ArgumentParser(description="龙虎榜明细查询")
    parser.add_argument("code", nargs="?", default="", help="证券代码（空 = 近期全部）")
    parser.add_argument("--days", type=int, default=7, help="查询天数（默认 7）")
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    result = get_lhb_detail(code=args.code, days=args.days)
    if not result or not result.get("items"):
        print(f"❌ 未获取到龙虎榜数据（code={args.code or '全部'} days={args.days}）")
        sys.exit(1)

    items = result["items"]
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return

    print(f"龙虎榜明细（{args.code or '全部'}，近 {args.days} 日，共 {len(items)} 条）")
    for it in items[:20]:
        date = it.get("date", "-")
        name = it.get("name", it.get("stock_name", "-"))
        close = it.get("close", it.get("price", "-"))
        pct = it.get("pct_chg", it.get("change_pct", "-"))
        reason = it.get("reason", it.get("lhb_reason", ""))
        print(f"  {date} {name} 收盘:{close} 涨跌:{pct}% {reason}")


if __name__ == "__main__":
    main()
