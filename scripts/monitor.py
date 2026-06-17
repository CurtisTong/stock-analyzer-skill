#!/usr/bin/env python3
"""
数据源健康检查和缓存监控。
用法:
  python3 scripts/monitor.py              # 完整健康检查
  python3 scripts/monitor.py --cache      # 缓存状态
  python3 scripts/monitor.py --sources    # 数据源状态（含健康度矩阵）
  python3 scripts/monitor.py --cleanup    # 清理过期缓存
  python3 scripts/monitor.py --json   # 输出结构化 JSON 日志
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CACHE_DIR, cache_cleanup


def check_cache_status() -> dict:
    """检查缓存目录状态。返回结构化数据。"""
    result = {
        "total_files": 0,
        "total_size_kb": 0.0,
        "expired_files": 0,
        "by_prefix": {},
    }
    if not CACHE_DIR.exists():
        return result

    files = list(CACHE_DIR.glob("*.cache"))
    total_size = sum(f.stat().st_size for f in files)
    expired = sum(1 for f in files if time.time() - f.stat().st_mtime > 21600)

    result["total_files"] = len(files)
    result["total_size_kb"] = round(total_size / 1024, 1)
    result["expired_files"] = expired

    # 按前缀统计
    prefixes: dict[str, int] = {}
    for f in files:
        prefix = f.name.split("_")[0] if "_" in f.name else "other"
        prefixes[prefix] = prefixes.get(prefix, 0) + 1
    result["by_prefix"] = prefixes

    return result


def check_sources() -> dict:
    """检查数据源可用性，返回健康度矩阵。"""
    from fetchers import get_quote_fetchers, get_kline_fetchers, get_finance_fetchers

    domains = {
        "quote": get_quote_fetchers(),
        "kline": get_kline_fetchers(),
        "finance": get_finance_fetchers(),
    }

    result = {}
    for domain, fetchers in domains.items():
        domain_result = []
        for f in fetchers:
            cb = f.circuit_breaker
            domain_result.append(
                {
                    "name": f.name,
                    "priority": f.priority,
                    "available": f.is_available(),
                    "state": cb.state.value,
                    "failure_count": cb.failure_count,
                    "last_failure": cb.last_failure_time,
                }
            )
        result[domain] = domain_result

    return result


def format_sources_table(sources: dict) -> str:
    """格式化数据源健康度矩阵为人类可读表格。"""
    lines = []
    for domain, fetchers in sources.items():
        lines.append(f"=== {domain} 数据源 ===")
        lines.append(
            f"{'名称':<25} {'优先级':>6} {'状态':<8} {'失败次数':>8} {'熔断状态':<10}"
        )
        lines.append("-" * 65)
        for f in fetchers:
            status = "✅" if f["available"] else "❌"
            state_label = {"closed": "正常", "open": "熔断", "half_open": "试探"}.get(
                f["state"], f["state"]
            )
            lines.append(
                f"  {f['name']:<23} {f['priority']:>6} {status:<8} {f['failure_count']:>8} {state_label:<10}"
            )
        lines.append("")
    return "\n".join(lines)


def run_health_check(log_json: bool = False) -> None:
    """完整健康检查。"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cache_info = check_cache_status()
    sources_info = check_sources()

    # 统计
    total_fetchers = sum(len(v) for v in sources_info.values())
    available_fetchers = sum(
        1 for v in sources_info.values() for f in v if f["available"]
    )
    failed_fetchers = total_fetchers - available_fetchers

    result = {
        "timestamp": timestamp,
        "cache": cache_info,
        "sources": sources_info,
        "summary": {
            "total_fetchers": total_fetchers,
            "available": available_fetchers,
            "failed": failed_fetchers,
            "cache_files": cache_info["total_files"],
            "cache_size_kb": cache_info["total_size_kb"],
        },
    }

    if log_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"🔍 stock-analyzer-skill 健康检查 ({timestamp})\n")

        print("--- 缓存状态 ---")
        print(f"  文件数: {cache_info['total_files']}")
        print(f"  总大小: {cache_info['total_size_kb']} KB")
        print(f"  过期数: {cache_info['expired_files']}")
        if cache_info["by_prefix"]:
            print("  按类型分布:")
            for prefix, count in sorted(cache_info["by_prefix"].items()):
                print(f"    {prefix}: {count} 个")

        print(f"\n--- 数据源状态 ({available_fetchers}/{total_fetchers} 可用) ---")
        print(format_sources_table(sources_info))

        print("--- 行业阈值配置 ---")
        thresholds_path = (
            Path(__file__).resolve().parent / "data" / "industry_thresholds.json"
        )
        if thresholds_path.exists():
            thresholds = json.loads(thresholds_path.read_text(encoding="utf-8"))
            industries = [k for k in thresholds.keys() if not k.startswith("_")]
            print(f"  已配置 {len(industries)} 个行业: {', '.join(industries)}")
        else:
            print("  ⚠ 行业阈值配置文件不存在")

        print(f"\n✅ 健康检查完成")


def main() -> None:
    from common.cache import cleanup_tmp_files

    cleanup_tmp_files()

    parser = argparse.ArgumentParser(description="数据源健康检查和缓存监控")
    parser.add_argument("--cache", action="store_true", help="显示缓存状态")
    parser.add_argument(
        "--sources", action="store_true", help="显示数据源状态（含健康度矩阵）"
    )
    parser.add_argument("--cleanup", action="store_true", help="清理过期缓存")
    parser.add_argument(
        "--json",
        "--log-json",
        action="store_true",
        dest="log_json",
        help="输出结构化 JSON 日志（推荐 --json，--log-json 已废弃）",
    )
    args = parser.parse_args()

    if args.cache:
        cache_info = check_cache_status()
        if args.log_json:
            print(json.dumps(cache_info, ensure_ascii=False, indent=2))
        else:
            print(f"缓存文件数: {cache_info['total_files']}")
            print(f"缓存总大小: {cache_info['total_size_kb']} KB")
            print(f"过期文件数: {cache_info['expired_files']}")
            if cache_info["by_prefix"]:
                print("\n按类型分布:")
                for prefix, count in sorted(cache_info["by_prefix"].items()):
                    print(f"  {prefix}: {count} 个")
    elif args.sources:
        sources_info = check_sources()
        if args.log_json:
            print(json.dumps(sources_info, ensure_ascii=False, indent=2))
        else:
            print(format_sources_table(sources_info))
    elif args.cleanup:
        cleaned = cache_cleanup()
        print(f"已清理 {cleaned} 个过期缓存文件")
    else:
        run_health_check(log_json=args.log_json)


if __name__ == "__main__":
    main()
