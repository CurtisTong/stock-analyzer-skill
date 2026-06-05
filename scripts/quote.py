#!/usr/bin/env python3
"""
实时行情查询（多数据源自动切换）。
数据源: 腾讯 → 东方财富 → 新浪 → efinance → akshare → tushare → 通达信
用法:
  quote.py sh600989                       # 单只，表格输出
  quote.py sh600989,sz000807,sh518880     # 批量（≤15/批）
  quote.py @codes.txt                     # 从文件读代码
  quote.py -j sh600989                    # JSON 输出
  quote.py --sources                      # 显示可用数据源
"""
import sys
import json
from common import (split_codes, batchify, normalize_quote_code, parallel_map, err,
                    cache_key_for_stock, cache_get, cache_set)
from fetchers import get_quote_manager, get_quote_fetchers


def fetch_batch(codes: list, use_cache: bool = True) -> list:
    """批量获取行情，支持缓存和自动故障切换。"""
    manager = get_quote_manager()

    if use_cache:
        cached_results = []
        uncached_codes = []
        for code in codes:
            key = cache_key_for_stock("quote", code)
            cached = cache_get(key, ttl_seconds=900)  # 15 分钟
            if cached is not None:
                try:
                    cached_results.append(json.loads(cached))
                except json.JSONDecodeError:
                    uncached_codes.append(code)
            else:
                uncached_codes.append(code)

        if not uncached_codes:
            return cached_results
        codes_to_fetch = uncached_codes
    else:
        codes_to_fetch = codes
        cached_results = []

    # 使用策略管理器获取数据
    results = []
    for code in codes_to_fetch:
        rec = manager.fetch(code)
        if rec:
            results.append(rec)

    # 写入缓存
    if use_cache:
        for rec in results:
            key = cache_key_for_stock("quote", rec["code"])
            cache_set(key, json.dumps(rec, ensure_ascii=False).encode())

    return cached_results + results


def main():
    if len(sys.argv) < 2:
        err("用法: quote.py <代码|@文件> [-j] [--sources]")
    args = sys.argv[1:]

    # 显示可用数据源
    if "--sources" in args:
        fetchers = get_quote_fetchers()
        print("可用行情数据源:")
        for f in fetchers:
            print(f"  - {f.name} (优先级 {f.priority})")
        return

    json_mode = "-j" in args
    args = [a for a in args if a not in ("-j", "--sources")]

    codes = [normalize_quote_code(c) for c in split_codes(args[0])]
    if not codes:
        err("未提供代码")

    batches = list(batchify(codes, 15))
    if len(batches) > 1:
        results = parallel_map(lambda b: fetch_batch(b, use_cache=True), batches, max_workers=4, timeout=30)
        all_records = []
        for batch in batches:
            all_records.extend(results.get(batch, []))
    else:
        all_records = fetch_batch(batches[0])

    if json_mode:
        print(json.dumps(all_records, ensure_ascii=False, indent=2))
        return

    if not all_records:
        print("(无数据)")
        return
    print(f"{'代码':<10} {'名称':<10} {'现价':>8} {'涨跌%':>7} {'PE':>7} {'换手%':>6} {'市值亿':>8}")
    print("-" * 60)
    for r in all_records:
        print(f"{r['code']:<10} {r['name']:<10} {r['price']:>8} {r['change_pct']:>7} {r['pe']:>7} {r['turnover']:>6} {r['total_cap']:>8}")

if __name__ == "__main__":
    main()
