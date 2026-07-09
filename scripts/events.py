#!/usr/bin/env python3
"""个股事件日历查询。

查询指定股票的近期事件（财报披露、解禁、分红、增减持、违规），用于 stock 分析时附加事件提醒。

用法：
  python3 scripts/events.py sh600519              # 查询近 30 日事件
  python3 scripts/events.py sh600519 --days 60    # 查询近 60 日事件
  python3 scripts/events.py sh600519 -j           # JSON 输出
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from data.event import get_events
from common import normalize_quote_code


def format_events_text(events: dict) -> str:
    """格式化事件为人类可读文本。"""
    lines = []
    lines.append(f"📅 近 {events['query_days']} 日事件日历 ({events['code']})")
    lines.append("")

    if events["earnings"]:
        lines.append("📊 财报披露:")
        for item in events["earnings"]:
            lines.append(
                f"  {item.get('disclosure_date', '?')} - {item.get('name', '?')} ({item.get('code', '?')})"
            )
        lines.append("")

    if events["lockup"]:
        lines.append("🔓 限售解禁:")
        for item in events["lockup"]:
            cap = item.get("lift_market_cap", 0)
            cap_str = f"{cap:.1f}亿" if cap > 0 else "?"
            lines.append(
                f"  {item.get('free_date', '?')} - {item.get('name', '?')} 解禁市值 {cap_str}"
            )
        lines.append("")

    if events["dividend"]:
        lines.append("💰 分红:")
        for item in events["dividend"]:
            bonus = item.get("bonus_per_share", 0)
            bonus_str = f"每股 {bonus:.4f} 元" if bonus > 0 else "?"
            lines.append(
                f"  {item.get('ex_date', '?')} - {item.get('name', '?')} {bonus_str}"
            )
        lines.append("")

    if events.get("shareholder"):
        lines.append("👤 大股东增减持:")
        for item in events["shareholder"][:3]:  # 最多显示 3 条
            direction = "增持" if item.get("direction") == "increase" else "减持"
            ratio = item.get("change_ratio", 0)
            lines.append(
                f"  {item.get('end_date', '?')} - {item.get('holder_name', '?')} {direction} {ratio:+.2f}%"
            )
        lines.append("")

    if events.get("violation"):
        lines.append("⚠️ 监管处罚:")
        for item in events["violation"][:3]:  # 最多显示 3 条
            lines.append(
                f"  {item.get('punish_date', '?')} - {item.get('reason', '?')[:30]}"
            )
        lines.append("")

    has_events = any(
        events.get(k)
        for k in ["earnings", "lockup", "dividend", "shareholder", "violation"]
    )
    if not has_events:
        lines.append(f"近 {events['query_days']} 日无重大事件")

    lines.append(f"\n🎯 {events['summary']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="个股事件日历查询")
    parser.add_argument("code", help="股票代码（如 sh600519）")
    parser.add_argument("--days", type=int, default=30, help="查询天数（默认 30）")
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()
    args.code = normalize_quote_code(args.code)

    events = get_events(args.code, args.days)

    if args.json:
        print(json.dumps(events, ensure_ascii=False, indent=2))
    else:
        print(format_events_text(events))


if __name__ == "__main__":
    main()
