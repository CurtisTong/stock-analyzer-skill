#!/usr/bin/env python3
"""
数据源健康检查和缓存监控。
用法:
  python3 scripts/monitor.py              # 完整健康检查
  python3 scripts/monitor.py --cache      # 缓存状态
  python3 scripts/monitor.py --sources    # 数据源状态
  python3 scripts/monitor.py --cleanup    # 清理过期缓存
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CACHE_DIR, cache_cleanup


def check_cache_status():
    """检查缓存目录状态。"""
    if not CACHE_DIR.exists():
        print("缓存目录不存在")
        return

    files = list(CACHE_DIR.glob("*.cache"))
    total_size = sum(f.stat().st_size for f in files)
    expired = sum(1 for f in files if time.time() - f.stat().st_mtime > 21600)

    print(f"缓存文件数: {len(files)}")
    print(f"缓存总大小: {total_size / 1024:.1f} KB")
    print(f"过期文件数: {expired}")

    # 按前缀统计
    prefixes = {}
    for f in files:
        prefix = f.name.split("_")[0] if "_" in f.name else "other"
        prefixes[prefix] = prefixes.get(prefix, 0) + 1
    if prefixes:
        print("\n按类型分布:")
        for prefix, count in sorted(prefixes.items()):
            print(f"  {prefix}: {count} 个")


def check_sources():
    """检查数据源可用性。"""
    from fetchers import get_quote_fetchers, get_kline_fetchers, get_finance_fetchers

    print("=== 行情数据源 ===")
    for f in get_quote_fetchers():
        status = "✅ 可用" if f.is_available() else "❌ 熔断"
        print(f"  {f.name} (优先级 {f.priority}) - {status}")

    print("\n=== K线数据源 ===")
    for f in get_kline_fetchers():
        status = "✅ 可用" if f.is_available() else "❌ 熔断"
        print(f"  {f.name} (优先级 {f.priority}) - {status}")

    print("\n=== 财务数据源 ===")
    for f in get_finance_fetchers():
        status = "✅ 可用" if f.is_available() else "❌ 熔断"
        print(f"  {f.name} (优先级 {f.priority}) - {status}")


def run_health_check():
    """完整健康检查。"""
    print("🔍 stock-analyzer-skill 健康检查\n")

    print("--- 缓存状态 ---")
    check_cache_status()

    print("\n--- 数据源状态 ---")
    check_sources()

    print("\n--- 行业阈值配置 ---")
    thresholds_path = Path(__file__).resolve().parent / "data" / "industry_thresholds.json"
    if thresholds_path.exists():
        thresholds = json.loads(thresholds_path.read_text(encoding="utf-8"))
        industries = [k for k in thresholds.keys() if not k.startswith("_")]
        print(f"  已配置 {len(industries)} 个行业: {', '.join(industries)}")
    else:
        print("  ⚠ 行业阈值配置文件不存在")

    print("\n✅ 健康检查完成")


def main():
    parser = argparse.ArgumentParser(description="数据源健康检查和缓存监控")
    parser.add_argument("--cache", action="store_true", help="显示缓存状态")
    parser.add_argument("--sources", action="store_true", help="显示数据源状态")
    parser.add_argument("--cleanup", action="store_true", help="清理过期缓存")
    args = parser.parse_args()

    if args.cache:
        check_cache_status()
    elif args.sources:
        check_sources()
    elif args.cleanup:
        cleaned = cache_cleanup()
        print(f"已清理 {cleaned} 个过期缓存文件")
    else:
        run_health_check()


if __name__ == "__main__":
    main()
