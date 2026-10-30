#!/usr/bin/env python3
"""情绪面板 CLI（v1.26 阶段 1）。

情绪因子的数据来源与可观测入口：

    python3 scripts/sentiment_panel.py refresh     # 拉取涨停/炸板池并落盘快照
    python3 scripts/sentiment_panel.py show         # 展示当日情绪面板
    python3 scripts/sentiment_panel.py show -j      # JSON 输出

快照是晋级率与板块 5 日轮动的前提（需要历史），建议每个交易日收盘后
跑一次 refresh（或用 cron 定时）。

命名说明：不叫 scripts/sentiment.py——仓库已有 scripts/technical/sentiment.py，
同名顶层模块会与包产生导入歧义（scripts/technical.py 与 scripts/technical/ 的
历史冲突即因此）。
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.cli_base import create_parser, handle_errors  # noqa: E402


def _fmt_pct(v, digits=1):
    return "N/A" if v is None else f"{v:.{digits}f}%"


def cmd_refresh(args):
    """拉取情绪面板并落盘快照。"""
    from data.sentiment_panel import refresh_and_save

    panel = refresh_and_save(args.date or "")
    if panel is None:
        print("❌ 情绪面板获取失败（涨停池/炸板池均为空）", file=sys.stderr)
        return 1
    print(
        f"✅ 情绪快照已更新 {panel['date']}："
        f"涨停 {panel['limit_up_count']} | 炸板 {panel['broken_count']} | "
        f"最高 {panel['max_height']} 连板"
    )
    return 0


def cmd_show(args):
    """展示当日情绪面板。"""
    from data.sentiment_panel import (
        get_latest_snapshot,
        get_promotion_rate,
        get_sector_heat,
    )

    snapshot = get_latest_snapshot()
    if not snapshot:
        print("❌ 无情绪快照，请先运行: python3 scripts/sentiment_panel.py refresh", file=sys.stderr)
        return 1

    heat = get_sector_heat(snapshot)
    top_sectors = sorted(heat.items(), key=lambda kv: -kv[1])[: args.top]
    promotion = get_promotion_rate(snapshot)

    if args.json_output:
        print(
            json.dumps(
                {
                    "date": snapshot.get("date"),
                    "limit_up_count": snapshot.get("limit_up_count"),
                    "broken_count": snapshot.get("broken_count"),
                    "max_height": snapshot.get("max_height"),
                    "height_distribution": snapshot.get("height_distribution"),
                    "median_chg_pct": snapshot.get("median_chg_pct"),
                    "promotion_rate": promotion,
                    "top_sectors": dict(top_sectors),
                    "stock_count": len(snapshot.get("stocks") or {}),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"📊 情绪面板（{snapshot.get('date')}）")
    print()
    print(f"涨停家数: {snapshot.get('limit_up_count')}")
    print(f"炸板家数: {snapshot.get('broken_count')}")
    print(f"最高连板: {snapshot.get('max_height')}")
    print(f"涨停中位涨幅: {_fmt_pct(snapshot.get('median_chg_pct'), 2)}")
    print(f"晋级率: {_fmt_pct(promotion * 100 if promotion is not None else None)}")
    dist = snapshot.get("height_distribution") or {}
    if dist:
        ladder = " → ".join(f"{k}板 {dist[k]}家" for k in sorted(dist, key=lambda x: int(x)))
        print(f"连板天梯: {ladder}")
    if top_sectors:
        print()
        print("板块热度 Top:")
        for name, pct in top_sectors:
            print(f"  {name:<10} {_fmt_pct(pct)}")
    return 0


def main():
    parser = create_parser(description="情绪面板（涨停/炸板/板块热度）")
    sub = parser.add_subparsers(dest="command", help="子命令")

    p_refresh = sub.add_parser("refresh", help="拉取并落盘当日情绪快照")
    p_refresh.add_argument("--date", default="", help="日期 YYYYMMDD（默认当日）")

    p_show = sub.add_parser("show", help="展示情绪面板")
    p_show.add_argument("--top", type=int, default=10, help="板块热度展示条数（默认 10）")
    p_show.add_argument("-j", "--json", action="store_true", dest="json_output", help="JSON 输出")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    cmds = {"refresh": cmd_refresh, "show": cmd_show}
    sys.exit(cmds[args.command](args) or 0)


if __name__ == "__main__":
    with handle_errors():
        main()
