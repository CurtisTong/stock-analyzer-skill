#!/usr/bin/env python3
"""
财务数据查询（多数据源自动切换）。
数据源: 东方财富 → efinance → akshare
用法:
  finance.py SH600989                       # 单只，默认最近 4 季
  finance.py SH600989 --periods 8           # 取最近 8 期（full/debate 推荐）
  finance.py -c SH600989,SZ000807           # 批量
  finance.py -j SH600989                    # JSON 输出
  finance.py --sources                      # 显示可用数据源
"""

import json
import argparse
from common import normalize_finance_code, parallel_map, err, DataError
from common.cli_base import handle_errors
from data import get_finance


def fetch(code: str, use_cache: bool = True, periods: int = 4) -> list:
    """返回最近 N 期财务数据（dict 列表，兼容旧接口）。

    Args:
        code: 股票代码
        use_cache: 是否使用磁盘缓存
        periods: 返回期数（默认 4；full/debate 模式调用方传 8）
    """
    records = get_finance(code, use_cache=use_cache, periods=periods)
    return [r.to_dict() for r in records]


def render_table(records: list) -> str:
    if not records:
        return "(无数据)"
    fields = [
        ("eps", "每股收益"),
        ("roe", "ROE%"),
        ("total_revenue", "营收亿"),
        ("parent_net_profit", "归母净利亿"),
        ("deducted_net_profit", "扣非亿"),
        ("revenue_yoy", "营收同比%"),
        ("net_profit_yoy", "净利同比%"),
        ("deducted_np_yoy", "扣非同比%"),
        ("gross_margin", "毛利率%"),
        ("net_margin", "净利率%"),
        ("debt_ratio", "负债率%"),
        ("bps", "每股净资产"),
        ("ocf_per_share", "每股现金流"),
        ("current_ratio", "流动比率"),
        ("quick_ratio", "速动比率"),
        ("revenue_qoq", "营收环比%"),
        ("profit_qoq", "净利环比%"),
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
    from common.cache import cleanup_tmp_files

    cleanup_tmp_files()

    parser = argparse.ArgumentParser(description="财务数据查询（多数据源自动切换）")
    parser.add_argument("code", nargs="?", help="股票代码（如 SH600989）")
    parser.add_argument("-c", "--codes", help="批量代码（逗号分隔）")
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    parser.add_argument("--sources", action="store_true", help="显示可用数据源")
    parser.add_argument(
        "--periods",
        type=int,
        default=4,
        help="返回期数（默认 4 季；full/debate 模式建议 8 季）",
    )
    args = parser.parse_args()

    if args.sources:
        from fetchers import get_finance_fetchers

        fetchers = get_finance_fetchers()
        print("可用财务数据源:")
        for f in fetchers:
            print(f"  - {f.name} (优先级 {f.priority})")
        return

    if args.codes:
        codes = args.codes.split(",")
    elif args.code:
        codes = [args.code]
    else:
        err("用法: finance.py <代码> [-c codes] [-j|--json] [--sources] [--periods N]")

    normalized_codes = [normalize_finance_code(c) for c in codes]

    if len(normalized_codes) > 1:
        results = parallel_map(
            lambda c: fetch(c, periods=args.periods), normalized_codes, timeout=30
        )
        all_results = {k: v for k, v in results.items() if v}
    else:
        all_results = {
            normalized_codes[0]: fetch(normalized_codes[0], periods=args.periods)
        }

    if args.json:
        print(json.dumps(all_results, ensure_ascii=False, indent=2))
        return

    for code, records in all_results.items():
        print(f"\n=== {code} ===")
        print(render_table(records))


if __name__ == "__main__":
    with handle_errors():
        main()
