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
from common import normalize_finance_code, parallel_map, err, DataError
from data import get_finance


def fetch(code: str, use_cache: bool = True) -> list:
    """返回最近 4 季的财务数据（dict 列表，兼容旧接口）。"""
    records = get_finance(code, use_cache=use_cache)
    return [r.to_dict() for r in records]


def render_table(records: list) -> str:
    if not records:
        return "(无数据)"
    fields = [
        ("eps", "每股收益"),
        ("roe", "ROE%"),
        ("revenue_yoy", "营收同比%"),
        ("net_profit_yoy", "净利同比%"),
        ("gross_margin", "毛利率%"),
        ("net_margin", "净利率%"),
        ("debt_ratio", "负债率%"),
        ("bps", "每股净资产"),
        ("ocf_per_share", "每股现金流"),
    ]
    lines = []
    header = " | ".join(["报告期"] + [label for _, label in fields])
    lines.append(header)
    lines.append("-" * len(header))
    for r in records:
        period = r.get("report_date", "?")
        values = [r.get(key, "-") for key, _ in fields]
        lines.append(" | ".join([period] + [str(v)[:8] for v in values]))
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        err("用法: finance.py <代码> [-c codes] [-j] [--sources]")
    args = sys.argv[1:]

    if "--sources" in args:
        from fetchers import get_finance_fetchers
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
    try:
        main()
    except DataError as e:
        sys.exit(1)
