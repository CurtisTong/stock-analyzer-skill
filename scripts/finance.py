#!/usr/bin/env python3
"""
财务数据查询（多数据源自动切换）。
数据源: 东方财富 → efinance → akshare
用法:
  finance.py SH600989                  # 单只，最近 4 季
  finance.py -c SH600989,SZ000807      # 批量
  finance.py -j SH600989               # JSON 输出
  finance.py --sources                 # 显示可用数据源
"""
import sys
import json
from common import (normalize_finance_code, parallel_map, err, EAST_MONEY_FIELDS)
from fetchers import get_finance_manager, get_finance_fetchers


def fetch(code: str, use_cache: bool = True) -> list:
    """返回最近 4 季的财务数据。"""
    manager = get_finance_manager()
    result = manager.fetch(code, use_cache=use_cache)
    return result if result else []


def render_table(records: list) -> str:
    if not records:
        return "(无数据)"
    keys = list(EAST_MONEY_FIELDS.keys())
    lines = []
    header = " | ".join(["报告期"] + [EAST_MONEY_FIELDS[k] for k in keys])
    lines.append(header)
    lines.append("-" * len(header))
    for r in records:
        period = r.get("REPORT_DATE") or r.get("NOTICE_DATE") or r.get("SECURITYCODE") or "?"
        for dk in ["REPORT_DATE", "REPORTDATETIME", "NOTICE_DATE", "DECLARE_DATE"]:
            if dk in r and r[dk]:
                period = str(r[dk])[:10]
                break
        values = [r.get(k, "-") for k in keys]
        lines.append(" | ".join([period] + [str(v)[:8] for v in values]))
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        err("用法: finance.py <代码> [-c codes] [-j] [--sources]")
    args = sys.argv[1:]

    if "--sources" in args:
        fetchers = get_finance_fetchers()
        print("可用财务数据源:")
        for f in fetchers:
            print(f"  - {f.name} (优先级 {f.priority})")
        return

    json_mode = "-j" in args
    args = [a for a in args if a not in ("-j", "--sources")]
    if not args:
        err("缺少代码")

    if args[0] == "-c":
        codes = args[1].split(",")
    else:
        codes = [args[0]]

    normalized_codes = [normalize_finance_code(c) for c in codes]

    if len(normalized_codes) > 1:
        results = parallel_map(fetch, normalized_codes, max_workers=4, timeout=30)
        all_results = {k: v for k, v in results.items() if v}
    else:
        all_results = {normalized_codes[0]: fetch(normalized_codes[0])}

    if json_mode:
        print(json.dumps(all_results, ensure_ascii=False, indent=2))
        return

    for code, records in all_results.items():
        print(f"\n=== {code} ===")
        print(render_table(records))


if __name__ == "__main__":
    main()
