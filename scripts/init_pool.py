#!/usr/bin/env python3
"""
首次安装初始化脚本 — 为每个板块拉取前 20 只股票。

用法:
  python3 scripts/init_pool.py              # 检测并初始化（已有数据则跳过）
  python3 scripts/init_pool.py --force      # 强制重新初始化
  python3 scripts/init_pool.py --top 30     # 每板块取 Top 30

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
    load_mapping,
    load_current_pool,
    refresh_pool,
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


def init_pool(top_n: int = 20, force: bool = False) -> bool:
    """初始化股票池。返回是否实际执行了初始化。"""
    # 检查是否已初始化
    if not force:
        populated, desc = is_pool_populated()
        if populated:
            print(f"✅ 股票池已存在（{desc}），跳过初始化")
            print("   如需刷新，运行: python3 scripts/refresh_pool.py")
            return False

    # 检查 API Token
    token = os.environ.get("EASTMONEY_API_TOKEN", "")
    if not token:
        print("⚠️  未设置 EASTMONEY_API_TOKEN，无法从东财 API 拉取数据")
        print()
        print("请按以下步骤操作：")
        print("  1. 设置环境变量: export EASTMONEY_API_TOKEN=你的token")
        print("     （东财 push2 API 的 ut 参数，可从网页版 F12 抓取）")
        print("  2. 运行初始化: python3 scripts/init_pool.py --force")
        print()
        print("或直接运行: python3 scripts/refresh_pool.py")
        return False

    # 执行初始化
    print(f"🚀 初始化股票池（每板块 Top {top_n}）...")
    print()

    try:
        new_pool = refresh_pool(top_n=top_n, dry_run=False, show_diff=False)
        total = sum(len(v) for v in new_pool.values())
        print()
        print(f"✅ 初始化完成: {len(new_pool)} 个板块，共 {total} 只股票")
        return True
    except Exception as e:
        print(f"\n❌ 初始化失败: {e}", file=sys.stderr)
        print("   可稍后重试: python3 scripts/init_pool.py --force")
        return False


def main():
    parser = argparse.ArgumentParser(description="首次安装初始化股票池")
    parser.add_argument("--force", "-f", action="store_true",
                        help="强制重新初始化（忽略已有数据）")
    parser.add_argument("--top", "-n", type=int, default=20,
                        help="每板块取 Top N（默认 20）")
    args = parser.parse_args()

    init_pool(top_n=args.top, force=args.force)


if __name__ == "__main__":
    main()
