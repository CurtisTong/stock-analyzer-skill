#!/usr/bin/env python3
"""资金面分析 CLI 入口。

用法:
  python3 scripts/chip.py <code> [选项]

选项:
  --margin         仅显示融资融券数据
  --holders        仅显示股东户数
  --top-holders    仅显示十大流通股东
  --chip           仅显示筹码分布（暂未实现）
  --all            显示全部（默认）
  -j, --json       JSON 输出
  --days N         融资融券天数（默认 20）

示例:
  python3 scripts/chip.py sh600989               # 全部资金面数据
  python3 scripts/chip.py sh600989 --margin -j   # 融资融券 JSON
  python3 scripts/chip.py sh600989 --holders     # 股东户数
"""

import sys
import json
import argparse
from pathlib import Path

# 添加 scripts 目录到 path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from data.chip import get_margin, get_holders, get_top_holders
from common import normalize_quote_code


def format_number(n, unit=""):
    """格式化数字显示。"""
    if abs(n) >= 1e8:
        return f"{n/1e8:.2f}亿{unit}"
    elif abs(n) >= 1e4:
        return f"{n/1e4:.2f}万{unit}"
    else:
        return f"{n:.2f}{unit}"


def format_change(n):
    """格式化变化率显示。"""
    if n > 0:
        return f"+{n:.2f}%"
    elif n < 0:
        return f"{n:.2f}%"
    else:
        return "0.00%"


def render_margin(data, days=20):
    """渲染融资融券数据。"""
    if not data:
        print("  该股票无融资融券数据或查询失败")
        return

    print("【融资融券】")
    print(
        f"  {'日期':<12} {'融资余额':>12} {'融资净买入':>12} {'融券余量':>10} {'杠杆情绪':>8}"
    )
    print("  " + "-" * 60)

    for item in data[:days]:
        # 计算杠杆情绪
        if item.rzjme > 0:
            sentiment = "偏多"
        elif item.rzjme < 0:
            sentiment = "偏空"
        else:
            sentiment = "中性"

        print(
            f"  {item.date:<12} {format_number(item.rzye):>12} {format_number(item.rzjme):>12} "
            f"{format_number(item.rqyl):>10} {sentiment:>8}"
        )

    # 汇总
    if len(data) >= 5:
        rzjme_5d = sum(d.rzjme for d in data[:5])
        print(f"\n  近5日融资净买入: {format_number(rzjme_5d)}")
        if all(d.rzjme > 0 for d in data[:5]):
            print("  趋势: 连续增加")
        elif all(d.rzjme < 0 for d in data[:5]):
            print("  趋势: 连续减少")
        else:
            print("  趋势: 波动")


def render_holders(data):
    """渲染股东户数数据。"""
    if not data:
        print("  该股票无股东户数数据或查询失败")
        return

    print("【股东户数】")
    print(
        f"  {'截止日期':<12} {'股东户数':>10} {'环比变化':>10} {'户均持股':>12} {'集中度':>8}"
    )
    print("  " + "-" * 58)

    for item in data:
        change_str = format_change(item.holder_num_change)
        print(
            f"  {item.end_date:<12} {item.holder_num:>10,} {change_str:>10} "
            f"{format_number(item.avg_amount, '股'):>12} {item.concentration:>8}"
        )


def render_top_holders(data):
    """渲染十大流通股东数据。"""
    if not data:
        print("  该股票无十大流通股东数据或查询失败")
        return

    print("【十大流通股东】")
    print(
        f"  {'排名':>4} {'股东名称':<24} {'类型':<10} {'持股(万股)':>10} {'占比(%)':>8} {'变动':>8}"
    )
    print("  " + "-" * 70)

    for item in data:
        # 截断股东名称
        name = (
            item.holder_name[:20] + "..."
            if len(item.holder_name) > 20
            else item.holder_name
        )
        change_str = (
            f"{item.change_type}{item.change:+.1f}"
            if item.change != 0
            else item.change_type
        )

        print(
            f"  {item.rank:>4} {name:<24} {item.holder_type:<10} "
            f"{item.hold_num:>10.1f} {item.hold_ratio:>8.2f} {change_str:>8}"
        )

    # 机构统计
    institutions = [h for h in data if h.is_institution]
    if institutions:
        total_ratio = sum(h.hold_ratio for h in institutions)
        print(f"\n  机构持股: {len(institutions)}家，合计占比 {total_ratio:.2f}%")


def main():
    parser = argparse.ArgumentParser(description="资金面分析")
    parser.add_argument("code", help="股票代码（如 sh600989）")
    parser.add_argument("--margin", action="store_true", help="仅显示融资融券")
    parser.add_argument("--holders", action="store_true", help="仅显示股东户数")
    parser.add_argument("--top-holders", action="store_true", help="仅显示十大流通股东")
    parser.add_argument(
        "--chip", action="store_true", help="仅显示筹码分布（暂未实现）"
    )
    parser.add_argument("--all", action="store_true", help="显示全部（默认）")
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    parser.add_argument("--days", type=int, default=20, help="融资融券天数（默认 20）")

    args = parser.parse_args()
    args.code = normalize_quote_code(args.code)

    # 判断是否显示全部
    show_all = not (args.margin or args.holders or args.top_holders or args.chip)

    result = {}

    # 获取数据
    if args.margin or show_all:
        result["margin"] = get_margin(args.code, days=args.days)
        result["margin_summary"] = {}

    if args.holders or show_all:
        result["holders"] = get_holders(args.code)
        result["holders_summary"] = {}

    if args.top_holders or show_all:
        result["top_holders"] = get_top_holders(args.code)

    # JSON 输出
    if args.json:
        output = {}
        if "margin" in result:
            output["margin"] = [d.to_dict() for d in result["margin"]]
            output["margin_summary"] = result.get("margin_summary", {})
        if "holders" in result:
            output["holders"] = [d.to_dict() for d in result["holders"]]
            output["holders_summary"] = result.get("holders_summary", {})
        if "top_holders" in result:
            output["top_holders"] = [d.to_dict() for d in result["top_holders"]]
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    # 表格输出
    print(f"\n{'═' * 60}")
    print(f"  资金面分析: {args.code}")
    print(f"{'═' * 60}\n")

    if args.margin or show_all:
        render_margin(result.get("margin", []), args.days)
        print()

    if args.holders or show_all:
        render_holders(result.get("holders", []))
        print()

    if args.top_holders or show_all:
        render_top_holders(result.get("top_holders", []))
        print()

    if args.chip:
        print("【筹码分布】")
        print("  暂未实现，敬请期待")
        print()


if __name__ == "__main__":
    main()
