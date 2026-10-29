#!/usr/bin/env python3
"""大宗交易查询。

查询个股或全市场的近期大宗交易记录（成交价量/金额/溢价率/买卖营业部），
用于机构动向分析：溢价成交 = 买方抢筹信号，折价大单 = 减持压力。

用法：
  python3 scripts/block_trade.py sh600519             # 个股近 30 日大宗交易
  python3 scripts/block_trade.py --days 3             # 全市场近 3 日
  python3 scripts/block_trade.py sh600989 -j          # JSON 输出
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import normalize_quote_code
from common.cli_base import create_parser
from common.exceptions import NetworkError, RateLimitError, HTTPStatusError, ParseError


def fetch_block_trade(code: str = "", days: int = 30) -> dict | None:
    """取大宗交易（fetch_with_breaker：熔断+限流；空 code = 全市场）。

    不走 DataFetcherManager——manager.fetch 要求非空 code（个股语义），
    与全市场查询语义冲突。
    """
    from fetchers import get_block_trade_fetchers
    from common import fetch_with_breaker

    fetcher = get_block_trade_fetchers()[0]
    code_arg = normalize_quote_code(code) if code else ""
    return fetch_with_breaker(fetcher, code_arg, days=days)


def format_text(result: dict) -> str:
    items = result.get("items", [])
    lines = [f"📦 大宗交易记录（{len(items)} 条）", ""]

    total_amt = sum(i.get("deal_amt", 0) for i in items)
    premium_deals = [i for i in items if i.get("premium_ratio") is not None and i["premium_ratio"] > 0]
    lines.append(
        f"合计成交 {total_amt / 1e8:.2f} 亿元 · 溢价成交 {len(premium_deals)} 笔"
        f" · 折价成交 {sum(1 for i in items if i.get('premium_ratio') is not None and i['premium_ratio'] < 0)} 笔"
    )
    lines.append("")

    for i in items[:15]:
        premium = i.get("premium_ratio")
        premium_str = f"{premium:+.2f}%" if premium is not None else "-"
        lines.append(
            f"  {i['date']} {i['name']}({i['code']})  "
            f"{i['deal_amt'] / 1e4:.0f}万元 @{i['deal_price']:.2f} 溢价{premium_str}  "
            f"{i.get('discount_note', '')}".rstrip()
        )
        if i.get("buyer") or i.get("seller"):
            lines.append(f"    买: {i.get('buyer', '?')[:20]} / 卖: {i.get('seller', '?')[:20]}")

    if len(items) > 15:
        lines.append(f"  ...（其余 {len(items) - 15} 条见 JSON 输出）")
    if result.get("truncated"):
        lines.append("  ⚠ 记录数超抓取上限，已截断")
    return "\n".join(lines)


def main():
    parser = create_parser(description="大宗交易查询")
    parser.add_argument("code", nargs="?", default="", help="股票代码（如 sh600519），空 = 全市场")
    parser.add_argument("--days", type=int, default=30, help="回看自然日（默认 30）")
    args = parser.parse_args()

    result = fetch_block_trade(args.code, args.days)
    if result is None:
        label = args.code or "全市场"
        print(f"近 {args.days} 日 {label} 无大宗交易记录")
        return

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text(result))


if __name__ == "__main__":
    main()
