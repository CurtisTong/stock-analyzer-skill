#!/usr/bin/env python3
"""
首次安装初始化脚本 — 为每个板块拉取前 20 只股票。

用法:
  python3 scripts/init_pool.py              # 检测并初始化（已有数据则跳过）
  python3 scripts/init_pool.py --force      # 强制重新初始化
  python3 scripts/init_pool.py --top 30     # 每板块取 Top 30
  python3 scripts/init_pool.py --full-market  # 初始化全市场股票池（all_stocks.json）

退出码始终为 0，不阻塞安装流程。
"""

import argparse
import json
import os
import sys

# 复用 refresh_pool 的核心逻辑
sys.path.insert(0, os.path.dirname(__file__))
from refresh_pool import (
    POOL_FILE,
    ALL_STOCKS_FILE,
    load_mapping,
    load_current_pool,
    load_default_pool,
    refresh_pool,
    init_from_default,
    fetch_all_market_stocks,
    save_all_market_stocks,
)

# 初始化阈值：低于此值视为未初始化
MIN_SECTORS = 10
MIN_STOCKS = 100


def is_pool_populated() -> tuple[bool, str]:
    """检查股票池是否已有足够数据。返回 (是否已初始化, 描述)。"""
    if not os.path.exists(POOL_FILE):
        return False, "股票池文件不存在"

    try:
        with open(POOL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False, "股票池文件损坏"

    sectors = {k: v for k, v in data.items() if not k.startswith("_")}
    total_stocks = sum(len(v) for v in sectors.values())

    if len(sectors) < MIN_SECTORS:
        return False, f"仅 {len(sectors)} 个板块（需要 ≥{MIN_SECTORS}）"
    if total_stocks < MIN_STOCKS:
        return False, f"仅 {total_stocks} 只股票（需要 ≥{MIN_STOCKS}）"

    return True, f"{len(sectors)} 个板块，{total_stocks} 只股票"


def init_pool(top_n: int = 20, force: bool = False, use_default: bool = False) -> bool:
    """初始化股票池。返回是否实际执行了初始化。

    Args:
        use_default: True 时直接使用预置默认数据，不访问 API
    """
    # 检查是否已初始化
    if not force:
        populated, desc = is_pool_populated()
        if populated:
            print(f"✅ 股票池已存在（{desc}），跳过初始化")
            print("   如需刷新，运行: python3 scripts/refresh_pool.py")
            return False

    # 显示 token 提示（非阻塞）
    token = os.environ.get("EASTMONEY_API_TOKEN", "")
    if not token:
        print("ℹ️  未设置 EASTMONEY_API_TOKEN，将尝试免费访问或使用预置数据")
        print("   如需最新数据，可设置: export EASTMONEY_API_TOKEN=你的token")
        print()

    # 执行初始化
    print(f"🚀 初始化股票池（每板块 Top {top_n}）...")
    print()

    try:
        if use_default:
            # 直接使用预置默认数据
            new_pool = init_from_default(top_n=top_n, dry_run=False)
        else:
            # 尝试从 API 获取，失败时自动 fallback 到默认数据
            new_pool = refresh_pool(top_n=top_n, dry_run=False, show_diff=False, use_default=True)

        if not new_pool:
            print("❌ 初始化失败: 无法获取股票数据", file=sys.stderr)
            return False

        total = sum(len(v) for v in new_pool.values())
        print()
        print(f"✅ 初始化完成: {len(new_pool)} 个板块，共 {total} 只股票")
        return True
    except Exception as e:
        print(f"\n❌ 初始化失败: {e}", file=sys.stderr)
        print("   可稍后重试: python3 scripts/init_pool.py --force")
        return False


def init_full_market(force: bool = False) -> bool:
    """初始化全市场股票池。返回是否实际执行了初始化。"""
    if not force and os.path.exists(ALL_STOCKS_FILE):
        try:
            with open(ALL_STOCKS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            total = data.get("_meta", {}).get("total_stocks", 0)
            if total > 0:
                print(f"✅ 全市场股票池已存在（{total} 只），跳过初始化")
                print("   如需刷新，运行: python3 scripts/refresh_pool.py --full-market")
                return False
        except (json.JSONDecodeError, OSError):
            pass  # 文件损坏，重新初始化

    print("🚀 初始化全市场股票池...")
    print()

    try:
        stocks_by_board = fetch_all_market_stocks()
        save_all_market_stocks(stocks_by_board)
        total = sum(len(v) for v in stocks_by_board.values())
        print(f"\n✅ 全市场初始化完成: 共 {total} 只股票")
        return True
    except Exception as e:
        print(f"\n❌ 全市场初始化失败: {e}", file=sys.stderr)
        print("   可稍后重试: python3 scripts/init_pool.py --full-market")
        return False


def main():
    parser = argparse.ArgumentParser(description="首次安装初始化股票池")
    parser.add_argument("--force", "-f", action="store_true",
                        help="强制重新初始化（忽略已有数据）")
    parser.add_argument("--top", "-n", type=int, default=20,
                        help="每板块取 Top N（默认 20）")
    parser.add_argument("--default", "-d", action="store_true",
                        help="使用预置默认数据（不访问 API，离线可用）")
    parser.add_argument("--full-market", action="store_true",
                        help="初始化全市场股票池（all_stocks.json，约 5000 只）")
    parser.add_argument("-j", "--json", action="store_true",
                        help="输出机器可读 JSON 摘要")
    args = parser.parse_args()

    result = {}
    if args.full_market:
        ret = init_full_market(force=args.force)
    else:
        ret = init_pool(top_n=args.top, force=args.force, use_default=args.default)
    result = ret if isinstance(ret, dict) else {"summary": str(ret) if ret else "completed"}

    if args.json:
        print(json.dumps({
            "status": "ok",
            "mode": "full_market" if args.full_market else "default",
            "args": {
                "force": args.force,
                "top": args.top,
                "default": args.default,
                "full_market": args.full_market,
            },
            "result": result,
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
