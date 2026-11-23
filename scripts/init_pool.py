#!/usr/bin/env python3
"""
首次安装初始化脚本 — 为每个板块拉取前 20 只股票。

用法:
  python3 scripts/init_pool.py              # 检测并初始化（已有数据则跳过）
  python3 scripts/init_pool.py --force      # 强制重新初始化
  python3 scripts/init_pool.py --top 30     # 每板块取 Top 30
  python3 scripts/init_pool.py --full-market  # 初始化全市场股票池（all_stocks.json）

退出码：[review P1-19] 失败退出 1（JSON 模式 status=error）；
成功或"已存在跳过"退出 0。JSON 模式业务日志走 stderr，stdout 仅输出 JSON。
"""

import argparse
from common.cli_base import create_parser, handle_errors
import json
import os
import sys
from common.exceptions.silent_fallback import log_silent_fallback

# 复用 refresh_pool 的核心逻辑
sys.path.insert(0, os.path.dirname(__file__))
from refresh_pool import (
    POOL_FILE,
    ALL_STOCKS_FILE,
    refresh_pool,
    init_from_default,
    fetch_all_market_stocks,
    save_all_market_stocks,
)

# 初始化阈值：低于此值视为未初始化
MIN_SECTORS = 10
MIN_STOCKS = 100

# [review P1-19] 最近一次初始化的细分状态：ok / skipped / error。
# 默认 error：main() 在调用业务函数前重置，若函数返回 False 但未打标记，
# 一律按失败处理（避免"失败仍 status=ok / 退出码 0"）。
_LAST_STATUS = "error"
# JSON 模式标志：业务日志改走 stderr，保证 stdout 是纯 JSON。
_JSON_MODE = False


def _mark_status(status: str) -> None:
    global _LAST_STATUS
    _LAST_STATUS = status


def _log(*args, **kwargs) -> None:
    """业务进度日志：JSON 模式走 stderr（review P1-19）。"""
    kwargs.setdefault("file", sys.stderr if _JSON_MODE else sys.stdout)
    print(*args, **kwargs)


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
            _mark_status("skipped")  # [review P1-19] 跳过 ≠ 失败，返回 False 但状态为 ok
            _log(f"✅ 股票池已存在（{desc}），跳过初始化")
            _log("   如需刷新，运行: python3 scripts/refresh_pool.py")
            return False

    # 显示 token 提示（非阻塞）
    token = os.environ.get("EASTMONEY_API_TOKEN", "")
    if not token:
        _log("ℹ️  未设置 EASTMONEY_API_TOKEN，将尝试免费访问或使用预置数据")
        _log("   如需最新数据，可设置: export EASTMONEY_API_TOKEN=你的token")
        _log()

    # 执行初始化
    _log(f"🚀 初始化股票池（每板块 Top {top_n}）...")
    _log()

    try:
        if use_default:
            # 直接使用预置默认数据
            new_pool = init_from_default(top_n=top_n, dry_run=False)
        else:
            # 尝试从 API 获取，失败时自动 fallback 到默认数据
            new_pool = refresh_pool(top_n=top_n, dry_run=False, show_diff=False, use_default=True)

        if not new_pool:
            _mark_status("error")
            _log("❌ 初始化失败: 无法获取股票数据", file=sys.stderr)
            return False

        total = sum(len(v) for v in new_pool.values())
        _log()
        _mark_status("ok")
        _log(f"✅ 初始化完成: {len(new_pool)} 个板块，共 {total} 只股票")
        return True
    except Exception as e:
        _mark_status("error")
        _log(f"\n❌ 初始化失败: {e}", file=sys.stderr)
        _log("   可稍后重试: python3 scripts/init_pool.py --force")
        return False


def init_full_market(force: bool = False) -> bool:
    """初始化全市场股票池。返回是否实际执行了初始化。"""
    if not force and os.path.exists(ALL_STOCKS_FILE):
        try:
            with open(ALL_STOCKS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            total = data.get("_meta", {}).get("total_stocks", 0)
            if total > 0:
                _mark_status("skipped")  # [review P1-19] 跳过 ≠ 失败
                _log(f"✅ 全市场股票池已存在（{total} 只），跳过初始化")
                _log("   如需刷新，运行: python3 scripts/refresh_pool.py --full-market")
                return False
        except (json.JSONDecodeError, OSError):
            pass  # 文件损坏，重新初始化

    _log("🚀 初始化全市场股票池...")
    _log()

    try:
        stocks_by_board = fetch_all_market_stocks()
        save_all_market_stocks(stocks_by_board)
        total = sum(len(v) for v in stocks_by_board.values())
        _mark_status("ok")
        _log(f"\n✅ 全市场初始化完成: 共 {total} 只股票")
        return True
    except Exception as e:
        log_silent_fallback("init_pool.init_full_market", e)
        _mark_status("error")
        _log(f"\n❌ 全市场初始化失败: {e}", file=sys.stderr)
        _log("   可稍后重试: python3 scripts/init_pool.py --full-market")
        return False


def main():
    parser = create_parser(description="首次安装初始化股票池")
    parser.add_argument("--force", "-f", action="store_true", help="强制重新初始化（忽略已有数据）")
    parser.add_argument("--top", "-n", type=int, default=20, help="每板块取 Top N（默认 20）")
    parser.add_argument(
        "--default",
        "-d",
        action="store_true",
        help="使用预置默认数据（不访问 API，离线可用）",
    )
    parser.add_argument(
        "--full-market",
        action="store_true",
        help="初始化全市场股票池（all_stocks.json，约 5000 只）",
    )
    args = parser.parse_args()

    # [review P1-19] 业务日志与机器输出分流
    global _JSON_MODE, _LAST_STATUS
    _JSON_MODE = bool(args.json_output)
    _LAST_STATUS = "error"  # 默认失败，业务函数成功/跳过后自行改标记

    if args.full_market:
        ret = init_full_market(force=args.force)
    else:
        ret = init_pool(top_n=args.top, force=args.force, use_default=args.default)

    # [review P1-19] 按返回值 + 细分标记决定 status，失败必须 exit 1
    if ret:
        status = "ok"
    elif _LAST_STATUS == "skipped":
        status = "ok"  # 已初始化跳过：不是失败，保持安装流程向前兼容
    else:
        status = "error"
    result = ret if isinstance(ret, dict) else {"summary": "completed" if ret else status}

    if args.json_output:
        print(
            json.dumps(
                {
                    "status": status,
                    "mode": "full_market" if args.full_market else "default",
                    "args": {
                        "force": args.force,
                        "top": args.top,
                        "default": args.default,
                        "full_market": args.full_market,
                    },
                    "result": result,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    if status == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
