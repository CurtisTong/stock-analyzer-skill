#!/usr/bin/env python3
"""可转债行情查询。

全市场可转债按双低值（价格+转股溢价率）排序，双低策略选债。

用法：
  python3 scripts/cb.py                    # 双低 Top 30
  python3 scripts/cb.py --top 10           # 双低 Top 10
  python3 scripts/cb.py 123291             # 查单只转债
  python3 scripts/cb.py -j                 # JSON 输出
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.cli_base import create_parser


def fetch_cb(code: str = "", top: int = 30) -> dict | None:
    from fetchers import get_cb_fetchers
    from common import fetch_with_breaker

    fetcher = get_cb_fetchers()[0]
    return fetch_with_breaker(fetcher, code, top=top)


def format_text(result: dict) -> str:
    items = result.get("items", [])
    lines = [f"🔄 可转债双低榜（{result.get('total', 0)} 只活跃，展示 {len(items)}）", ""]
    lines.append("代码      名称        现价      溢价率%   双低值")
    lines.append("--------  ----------  --------  --------  ------")
    for i in items[:30]:
        prem = f"{i['premium_ratio']:.2f}" if i["premium_ratio"] is not None else "-"
        dl = f"{i['double_low']:.2f}" if i["double_low"] is not None else "-"
        lines.append(f"{i['code']:<9}{i['name']:<11}{i['price']:<10.2f}{prem:<10}{dl}")
    if result.get("truncated"):
        lines.append("  ⚠ 超抓取上限，已截断")
    lines.append("")
    lines.append("双低值 = 现价 + 转股溢价率（越低性价比越高，双低策略选债口径）")
    return "\n".join(lines)


def main():
    parser = create_parser(description="可转债双低查询")
    parser.add_argument("code", nargs="?", default="", help="转债代码（可选）")
    parser.add_argument("--top", type=int, default=30, help="展示条数（默认 30）")
    args = parser.parse_args()

    result = fetch_cb(args.code.strip(), args.top)
    if result is None:
        print("可转债数据不可用（接口异常或无活跃转债）")
        return

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text(result))


if __name__ == "__main__":
    main()
