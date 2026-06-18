"""
数据源健康检查与监控。
提供数据源状态查询、缓存命中率、熔断器状态等功能。
"""
import os
import sys
from pathlib import Path

# 添加 scripts 目录到 path

import json
import time
from datetime import datetime

from common import get_circuit_breaker, CircuitState


def get_fetcher_health() -> dict:
    """获取所有数据源的熔断器健康状态。"""
    from fetchers import (
        get_quote_fetchers, get_kline_fetchers, get_finance_fetchers,
        get_flow_fetchers, get_lhb_fetchers, get_event_fetchers,
    )
    
    categories = {
        "行情": get_quote_fetchers,
        "K线": get_kline_fetchers,
        "财务": get_finance_fetchers,
        "资金流向": get_flow_fetchers,
        "龙虎榜": get_lhb_fetchers,
        "事件日历": get_event_fetchers,
    }
    
    result = {"timestamp": datetime.now().isoformat(), "sources": {}}
    
    for cat_name, fetcher_fn in categories.items():
        try:
            fetchers = fetcher_fn()
            result["sources"][cat_name] = []
            for f in fetchers:
                cb = f.circuit_breaker
                result["sources"][cat_name].append({
                    "name": f.name,
                    "priority": f.priority,
                    "state": cb.state.value,
                    "failure_count": cb.failure_count,
                    "available": cb.can_execute(),
                })
        except Exception as e:
            result["sources"][cat_name] = {"error": str(e)}
    
    return result


def get_cache_stats() -> dict:
    """获取缓存统计信息。"""
    from common import cache

    cache_dir = cache.CACHE_DIR
    if not cache_dir.exists():
        return {"error": "缓存目录不存在"}

    # 配置阈值（可通过环境变量调整）
    max_size_mb = int(os.getenv("STOCK_CACHE_MAX_SIZE_MB", "500"))

    stats = {
        "cache_dir": str(cache_dir),
        "total_files": 0,
        "total_size_bytes": 0,
        "by_prefix": {},
        "max_size_mb": max_size_mb,
        "warnings": [],
    }

    for f in cache_dir.iterdir():
        if f.is_file() and f.suffix == ".cache":
            stats["total_files"] += 1
            size = f.stat().st_size
            stats["total_size_bytes"] += size

            # 按前缀统计
            name = f.stem
            prefix = name.split("_")[0]
            if prefix not in stats["by_prefix"]:
                stats["by_prefix"][prefix] = {"count": 0, "size": 0}
            stats["by_prefix"][prefix]["count"] += 1
            stats["by_prefix"][prefix]["size"] += size

    # 格式化大小
    for prefix, data in stats["by_prefix"].items():
        data["size_mb"] = round(data["size"] / 1024 / 1024, 2)

    total_mb = round(stats["total_size_bytes"] / 1024 / 1024, 2)
    stats["total_size_mb"] = total_mb
    del stats["total_size_bytes"]

    # 阈值告警
    if total_mb > max_size_mb:
        stats["warnings"].append(f"⚠️ 缓存大小 {total_mb}MB 超过阈值 {max_size_mb}MB，建议执行 --cleanup")
    if stats["total_files"] > 2000:
        stats["warnings"].append(f"⚠️ 缓存文件数 {stats['total_files']} 过多，建议清理")

    return stats


def health_check() -> dict:
    """执行完整健康检查。"""
    return {
        "timestamp": datetime.now().isoformat(),
        "fetcher_health": get_fetcher_health(),
        "cache_stats": get_cache_stats(),
    }


def print_health_report():
    """打印健康检查报告。"""
    report = health_check()
    
    print("=" * 60)
    print("📊 stock-analyzer-skill 健康检查报告")
    print(f"时间: {report['timestamp']}")
    print("=" * 60)
    
    # 数据源状态
    print("\n🔌 数据源状态:")
    print("-" * 40)
    fetcher_health = report["fetcher_health"]
    for cat, sources in fetcher_health.get("sources", {}).items():
        print(f"\n【{cat}】")
        if isinstance(sources, dict) and "error" in sources:
            print(f"  ❌ 加载失败: {sources['error']}")
        else:
            for s in sources:
                status = "✅ 可用" if s.get("available") else "❌ 熔断"
                state_icon = {"closed": "🟢", "open": "🔴", "half_open": "🟡"}.get(s.get("state", ""), "⚪")
                print(f"  {state_icon} {s['name']:<20} {status:<10} 失败:{s.get('failure_count', 0)}")
    
    # 缓存状态
    print("\n💾 缓存状态:")
    print("-" * 40)
    cache_stats = report.get("cache_stats", {})
    if "error" in cache_stats:
        print(f"  ❌ {cache_stats['error']}")
    else:
        print(f"  缓存目录: {cache_stats.get('cache_dir', 'N/A')}")
        print(f"  总文件数: {cache_stats.get('total_files', 0)}")
        print(f"  总大小: {cache_stats.get('total_size_mb', 0)} MB / {cache_stats.get('max_size_mb', 500)} MB")
        print(f"  按类型:")
        for prefix, data in cache_stats.get("by_prefix", {}).items():
            print(f"    - {prefix}: {data['count']} 个 ({data['size_mb']} MB)")

        # 显示告警
        warnings = cache_stats.get("warnings", [])
        if warnings:
            print("\n  ⚠️ 告警:")
            for w in warnings:
                print(f"    {w}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if "--cleanup" in args:
        from common import cache
        max_age = 86400  # 默认 24 小时
        for i, a in enumerate(args):
            if a == "--max-age" and i + 1 < len(args):
                try:
                    max_age = int(args[i + 1])
                except ValueError:
                    pass
        count = cache.cleanup(max_age_seconds=max_age)
        print(f"已清理 {count} 个过期缓存文件（>{max_age}s）")
    elif "--json" in args:
        print(json.dumps(health_check(), ensure_ascii=False, indent=2))
    else:
        print_health_report()
