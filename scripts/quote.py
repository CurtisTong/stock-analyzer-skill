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

import json
import argparse
from common import (
    split_codes,
    batchify,
    normalize_quote_code,
    parallel_map,
    err,
    DataError,
)
from common.cli_base import handle_errors
from data import get_quotes


def fetch_batch(codes: list, use_cache: bool = True) -> list:
    """批量获取行情，返回 dict 列表（兼容旧接口）。"""
    quotes = get_quotes(codes, use_cache=use_cache)
    return [q.to_dict() for q in quotes]


def main():
    from common.cache import cleanup_tmp_files

    cleanup_tmp_files()

    parser = argparse.ArgumentParser(description="实时行情查询（多数据源自动切换）")
    parser.add_argument(
        "code", nargs="?", help="股票代码（如 sh600989）或 @codes.txt 文件路径"
    )
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    parser.add_argument("--sources", action="store_true", help="显示可用数据源")
    args = parser.parse_args()

    if args.sources:
        from fetchers import get_quote_fetchers

        fetchers = get_quote_fetchers()
        print("可用行情数据源:")
        for f in fetchers:
            print(f"  - {f.name} (优先级 {f.priority})")
        return

    if not args.code:
        err("用法: quote.py <代码|@文件> [-j|--json] [--sources]")

    codes = [normalize_quote_code(c) for c in split_codes(args.code)]
    if not codes:
        err("未提供代码")

    batches = list(batchify(codes, 15))
    if len(batches) > 1:
        results = parallel_map(
            lambda b: fetch_batch(b, use_cache=True), batches, timeout=30
        )
        all_records = []
        for batch in batches:
            all_records.extend(results.get(batch) or [])
    else:
        all_records = fetch_batch(batches[0])

    if args.json:
        print(json.dumps(all_records, ensure_ascii=False, indent=2))
        return

    if not all_records:
        print("(无数据)")
        return
    print(
        f"{'代码':<10} {'名称':<10} {'现价':>8} {'涨跌%':>7} {'PE':>7} {'换手%':>6} {'市值亿':>8}"
    )
    print("-" * 60)
    for r in all_records:
        print(
            f"{r['code']:<10} {r['name']:<10} {r['price']:>8} {r['change_pct']:>7} {r['pe']:>7} {r['turnover']:>6} {r['total_cap']:>8}"
        )


if __name__ == "__main__":
    with handle_errors():
        main()
