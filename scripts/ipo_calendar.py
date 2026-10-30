#!/usr/bin/env python3
"""新股/新债日历查询。

查询近期新股新债的申购/中签号/缴款日/上市等事件，配合打新决策。

用法：
  python3 scripts/ipo_calendar.py              # 未来 30 天新股日历
  python3 scripts/ipo_calendar.py --days 7     # 未来 7 天
  python3 scripts/ipo_calendar.py 688827       # 只看某代码事件
  python3 scripts/ipo_calendar.py -j           # JSON 输出
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.cli_base import create_parser


def fetch_ipo_calendar(code: str = "", days: int = 30) -> dict | None:
    from fetchers import get_ipo_fetchers
    from common import fetch_with_breaker

    fetcher = get_ipo_fetchers()[0]
    return fetch_with_breaker(fetcher, code, days=days)


def format_text(days: int, result: dict) -> str:
    items = result.get("items", [])
    # 按事件类型分组
    by_type: dict[str, list] = {}
    for i in items:
        by_type.setdefault(i["event_type"], []).append(i)

    lines = [f"📅 新股/新债日历（未来 {days} 日，共 {len(items)} 条事件）", ""]

    type_order = ["申购", "中签号", "中签率", "缴款日", "上市"]
    listed = set()
    for tp in type_order:
        if tp not in by_type:
            continue
        listed.add(tp)
        lines.append(f"◆ {tp}")
        for i in sorted(by_type[tp], key=lambda x: x["date"])[:15]:
            lines.append(f"  {i['date']}  {i['name']}({i['code']}) [{i['security_type']}]")
        extra = len(by_type[tp]) - 15
        if extra > 0:
            lines.append(f"  …其余 {extra} 条见 JSON 输出")
        lines.append("")
    # 白名单外的事件类型（如"股权登记"）不能静默消失——归入"其它"桶
    others = [tp for tp in by_type if tp not in listed]
    if others:
        lines.append("◆ 其它事件")
        for tp in sorted(others):
            for i in sorted(by_type[tp], key=lambda x: x["date"])[:15]:
                lines.append(f"  {i['date']}  {tp}  {i['name']}({i['code']}) [{i['security_type']}]")
            extra = len(by_type[tp]) - 15
            if extra > 0:
                lines.append(f"  …其余 {extra} 条见 JSON 输出")
        lines.append("")
    if result.get("truncated"):
        lines.append("  ⚠ 事件超抓取上限，已截断")
    return "\n".join(lines)


def main():
    parser = create_parser(description="新股/新债日历查询")
    parser.add_argument("code", nargs="?", default="", help="股票/转债代码（可选）")
    parser.add_argument("--days", type=int, default=30, help="未来回看天数（默认 30）")
    args = parser.parse_args()

    code = args.code.strip() if args.code else ""
    result = fetch_ipo_calendar(code, args.days)
    if result is None:
        label = code or "近期"
        print(f"{label} 无新股/新债日历事件")
        return

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text(args.days, result))


if __name__ == "__main__":
    main()
