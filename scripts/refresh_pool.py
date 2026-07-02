#!/usr/bin/env python3
"""
股票池自动刷新脚本 — 从东财 push2 API 拉取板块成分股。

用法:
  python3 scripts/refresh_pool.py                     # 刷新全部板块
  python3 scripts/refresh_pool.py --sector 机器人      # 只刷新指定板块
  python3 scripts/refresh_pool.py --top 30             # 每板块取 Top 30
  python3 scripts/refresh_pool.py --sort cap           # 按市值排序（默认 amount）
  python3 scripts/refresh_pool.py --dry-run            # 只打印不写入
  python3 scripts/refresh_pool.py --diff               # 对比当前池显示变更

数据源: 东财 push2.eastmoney.com 板块成分股 API

业务逻辑已下沉到 data/pool.py，本文件只保留 CLI 入口（print_diff + main）
和向后兼容的 re-export。
"""

import argparse
import json
import os
import sys

# 复用 common.py 的分类工具（消除与 _classify_board/_infer_exchange 的重复）
sys.path.insert(0, os.path.dirname(__file__))
from common import board_type, infer_exchange
from data.pool import (
    # 常量
    POOL_FILE,
    ALL_STOCKS_FILE,
    MAPPING_FILE,
    DEFAULT_POOL_FILE,
    API_BASE,
    API_TOKEN,
    FIELDS,
    XUANGU_API_BASE,
    XUANGU_FIELDS,
    # API 调用
    fetch_board_stocks,
    fetch_multiple_boards,
    fetch_all_market_stocks,
    save_all_market_stocks,
    # 过滤
    is_st,
    passes_filter,
    # 排序与筛选
    sort_stocks,
    build_sector_pool,
    build_dividend_pool,
    # 主流程
    load_mapping,
    load_default_pool,
    load_current_pool,
    refresh_pool,
    init_from_default,
)

# ---------- 向后兼容：_classify_board / _infer_exchange ----------
# 原实现与 common.board_type / common.infer_exchange 重复，此处改为转发，
# 消除重复同时保持 refresh_pool._classify_board 的导入兼容性。
_classify_board = board_type
_infer_exchange = infer_exchange

# 硬过滤阈值别名（向后兼容）
from strategies.filters import PRE_SCREEN_FILTER as FILTER  # noqa: F401


# ---------- CLI 输出 ----------


def print_diff(current: dict, new_pool: dict):
    """打印新旧池对比"""
    print("\n" + "=" * 60)
    print("📊 股票池变更对比")
    print("=" * 60)

    all_sectors = sorted(set(list(current.keys()) + list(new_pool.keys())))

    for sector in all_sectors:
        old = set(current.get(sector, []))
        new = set(new_pool.get(sector, []))
        added = new - old
        removed = old - new
        if not added and not removed:
            continue
        print(f"\n【{sector}】")
        if added:
            print(f"  + 新增 {len(added)}: {', '.join(sorted(added))}")
        if removed:
            print(f"  - 移除 {len(removed)}: {', '.join(sorted(removed))}")

    total_old = sum(len(v) for v in current.values())
    total_new = sum(len(v) for v in new_pool.values())
    print(f"\n总计: {total_old} → {total_new} ({total_new - total_old:+d})")


# ---------- CLI ----------


def main():
    from common.cache import cleanup_tmp_files

    cleanup_tmp_files()

    parser = argparse.ArgumentParser(description="股票池自动刷新")
    parser.add_argument("--sector", "-s", nargs="+", help="只刷新指定板块")
    parser.add_argument(
        "--top", "-n", type=int, default=20, help="每板块取 Top N（默认 20）"
    )
    parser.add_argument(
        "--sort",
        choices=["amount", "cap", "pe", "turnover"],
        default="amount",
        help="排序方式（默认 amount 成交额）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    parser.add_argument("--diff", action="store_true", help="对比当前池显示变更")
    parser.add_argument(
        "--default", action="store_true", help="使用预置默认数据初始化（不访问 API）"
    )
    parser.add_argument(
        "--full-market",
        action="store_true",
        help="拉取全市场 A 股列表（约 5000 只），保存到 all_stocks.json",
    )
    parser.add_argument(
        "-j", "--json", action="store_true", help="输出机器可读 JSON 摘要"
    )
    args = parser.parse_args()

    if args.full_market:
        ret = fetch_all_market_stocks()
        if not args.dry_run:
            save_all_market_stocks(ret)
        result = {"mode": "full_market", "count": len(ret) if ret else 0}
    elif args.default:
        ret = init_from_default(top_n=args.top, dry_run=args.dry_run)
        result = {"mode": "default", "top_n": args.top}
    else:
        # diff 模式下先取当前池用于 CLI 对比输出
        current = load_current_pool() if args.diff else None
        ret = refresh_pool(
            sectors=args.sector,
            top_n=args.top,
            sort_by=args.sort,
            dry_run=args.dry_run,
            show_diff=args.diff,
        )
        # CLI 层额外打印 diff（业务层已通过 logging 输出，这里给用户可见的格式化输出）
        if args.diff and current is not None:
            print_diff(current, ret)
        result = {
            "mode": "refresh",
            "sectors": args.sector or "all",
            "top_n": args.top,
            "sort_by": args.sort or "default",
        }

    if args.json:
        import json as _json

        print(_json.dumps({"status": "ok", **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
