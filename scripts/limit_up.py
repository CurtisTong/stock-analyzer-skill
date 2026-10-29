#!/usr/bin/env python3
"""涨停池与涨停原因归因查询。

查询指定交易日的涨停池（涨停原因/板型/封板质量/回封标记），
短线情绪复盘与题材轮动判断的入口数据。

用法：
  python3 scripts/limit_up.py                  # 当日涨停池
  python3 scripts/limit_up.py --date 20261028  # 指定交易日
  python3 scripts/limit_up.py sh600519         # 查个股是否在池（含原因）
  python3 scripts/limit_up.py -j               # JSON 输出
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import normalize_quote_code
from common.cli_base import create_parser
from common.exceptions import NetworkError, RateLimitError, HTTPStatusError, ParseError


def fetch_limit_up(code: str = "", date: str = "") -> dict | None:
    """取涨停池（fetch_with_breaker：熔断+限流；空 code = 全市场）。"""
    from fetchers import get_limit_up_fetchers
    from common import fetch_with_breaker

    fetcher = get_limit_up_fetchers()[0]
    code_arg = normalize_quote_code(code) if code else ""
    return fetch_with_breaker(fetcher, code_arg, date=date)


def format_text(result: dict) -> str:
    items = result.get("items", [])
    seal_clean = [i for i in items if i["open_num"] == 0]  # 未开板
    again = [i for i in items if i.get("is_again_limit")]

    lines = [f"🔥 涨停池 {result.get('date', '')}（{len(items)} 只）", ""]
    lines.append(
        f"硬板（未开板）{len(seal_clean)} 只 · 回封 {len(again)} 只 · " f"炸板过 {len(items) - len(seal_clean)} 只"
    )
    lines.append("")

    for i in items[:20]:
        lines.append(
            f"  {i['name']}({i['code']}) {i['change_pct']:+.1f}%  "
            f"[{i['limit_up_type']}|{i['high_days']}] 开板{i['open_num']}次"
            f"{' · 回封' if i.get('is_again_limit') else ''}  首封{i.get('first_time', '-')}"
        )
        if i.get("reason_type"):
            lines.append(f"    原因: {i['reason_type']}")

    if len(items) > 20:
        lines.append(f"  ...（其余 {len(items) - 20} 只见 JSON 输出）")
    if result.get("truncated"):
        lines.append("  ⚠ 超抓取上限，已截断")
    return "\n".join(lines)


def main():
    parser = create_parser(description="涨停池与涨停原因查询")
    parser.add_argument("code", nargs="?", default="", help="股票代码（可选，查个股在池状态）")
    parser.add_argument("--date", default="", help="交易日 YYYYMMDD（默认今天）")
    args = parser.parse_args()

    code = normalize_quote_code(args.code) if args.code else ""
    result = fetch_limit_up(code, args.date)
    if result is None:
        label = code or args.date or "今日"
        print(f"{label} 无涨停池数据（非交易日或接口无数据）")
        return

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text(result))


if __name__ == "__main__":
    main()
