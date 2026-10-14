#!/usr/bin/env python3
"""成本分布（筹码分布）分析——获利盘/套牢盘、平均成本、主密集区、上方抛压。

模型：三角分布 + 换手衰减（详见 scripts/technical/chip_distribution.py）。
取数：优先不复权 K 线（筹码成本=实际成交价），详见 scripts/data/chip_dist.py。
结果为**模型推算值**，非交易所观测数据。

用法:
  chip_dist.py sh600989                              # 单股
  chip_dist.py sh600989 -j                           # 单股 JSON
  chip_dist.py --codes sh600989,sz300274 -j          # 批量（组合）
  chip_dist.py --pool 军工 -j                        # 板块池（复用 sector_stocks.json）
  chip_dist.py --pool 军工,半导体 --tier 深度套牢 -j   # 板块 + 档位筛选
  chip_dist.py --codes ... --sort rebound --limit 10
  chip_dist.py --sources                             # 显示 K 线数据源

说明：
- 板块池可用名见 scripts/data/sector_stocks.json（金融/消费/医药/资源/电力/石化/高股息/
  科技/机器人/PCB-AI算力/军工/半导体/新能源/光伏）。
- **无指数成分股数据源**，市场/指数层面请用 `--pool` 或显式 `--codes`；全市场逐只取
  250 日 K 线成本过高，不建议。
- 底层 K 线走 common.cache 缓存，重复运行很快，无需额外缓存层。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import json  # noqa: E402
from datetime import datetime  # noqa: E402

from common import err  # noqa: E402
from common.cli_base import create_parser, handle_errors  # noqa: E402
from data.chip_dist import DEFAULT_BINS, DEFAULT_WINDOW, get_chip_distribution  # noqa: E402

_SORT_KEYS = {
    "trapped": lambda it: -(it.get("trapped_ratio") or 0),
    "rebound": lambda it: -(it.get("rebound_to_main_pct") or -999),
    "wall": lambda it: -(it.get("wall_mass_pct") or 0),
    "profit": lambda it: -(it.get("profit_ratio") or 0),
}


def _num(value, spec: str = "", dash: str = "-") -> str:
    """格式化数值，None 用占位符（占位符同样套用宽度 spec 以保持列对齐）。

    现价上方无筹码密集区时 main_cluster 为 None，需反弹/墙厚随之缺失。
    """
    return format(dash if value is None else value, spec)


def analyze_one(code: str, window: int, bins: int) -> dict:
    """计算单只标的的成本分布，返回 {meta, chip}。"""
    chip, meta = get_chip_distribution(code, window=window, bins=bins)
    return {"meta": meta, "chip": chip}


def _resolve_codes(args) -> list:
    """汇总 --pool / --codes / 位置参数 的代码列表（去重保序）。"""
    codes: list = []
    if args.pool:
        from data.pool import load_current_pool

        pools = load_current_pool()
        for name in (n.strip() for n in args.pool.split(",") if n.strip()):
            members = pools.get(name)
            if not members:
                available = ", ".join(k for k in pools if not k.startswith("_"))
                err(f"未找到板块池 '{name}'（可用: {available}）")
                continue
            codes.extend(members)
    raw = args.codes or args.code
    if raw:
        codes.extend(c.strip() for c in raw.split(",") if c.strip())

    seen: set = set()
    out: list = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _apply_filters(items: list, args) -> list:
    """按档位/获利盘/需反弹过滤。

    取数失败项不受筛选影响、始终保留——组合场景下"静默少一只"比"多一行错"更危险。
    """
    tiers = {t.strip() for t in args.tier.split(",")} if args.tier else None
    out = []
    for it in items:
        if not it.get("error"):
            if tiers and it.get("tier") not in tiers:
                continue
            if args.min_profit is not None and (it.get("profit_ratio") or 0) < args.min_profit:
                continue
            if args.max_rebound is not None:
                rebound = it.get("rebound_to_main_pct")
                if rebound is None or rebound > args.max_rebound:
                    continue
        out.append(it)
    return out


def _flat(one: dict) -> dict:
    """把 {meta, chip} 压平成批量排序用的一行。"""
    m, c = one["meta"], one.get("chip") or {}
    main = c.get("main_cluster") or {}
    return {
        "code": m["code"],
        "price": c.get("price"),
        "profit_ratio": c.get("profit_ratio"),
        "trapped_ratio": c.get("trapped_ratio"),
        "avg_cost": c.get("avg_cost"),
        "price_vs_avg_cost_pct": c.get("price_vs_avg_cost_pct"),
        "rebound_to_main_pct": c.get("rebound_to_main_pct"),
        "wall_mass_pct": main.get("mass_pct"),
        "wall_thick": c.get("wall_thick"),
        "main_peak": main.get("peak"),
        "tier": c.get("tier"),
        "adjust": m.get("adjust"),
        "degraded": m.get("degraded") or [],
        "notes": m.get("notes") or [],
        "error": m.get("error"),
    }


def render_single(one: dict) -> str:
    m, c = one["meta"], one.get("chip")
    lines = [f"成本分布（筹码） {m['code']}  {m['as_of']}"]
    if not c:
        lines.append(f"  计算失败: {m.get('error', '未知')}")
        return "\n".join(lines)
    main = c.get("main_cluster")
    if main:
        band = main.get("band") or ["-", "-"]
        cluster = (
            f"  主密集区 {band[0]} - {band[1]}（峰 {main.get('peak')}，占流通盘 {main.get('mass_pct')}%）"
            f" | 需反弹 {_num(c.get('rebound_to_main_pct'), '+.1f')}%"
        )
    else:
        cluster = "  主密集区 无（现价上方无筹码密集区，反弹第一压力=均线）"
    lines += [
        f"  现价 {c['price']} | 平均成本 {c['avg_cost']} ({_num(c.get('price_vs_avg_cost_pct'), '+.1f')}%)",
        f"  获利盘 {c['profit_ratio']}% / 套牢盘 {c['trapped_ratio']}%  [{c['tier']}]",
        f"  90% 成本区间 {c['cost_range_90']['low']} - {c['cost_range_90']['high']}",
        cluster,
        f"  窗口换手 {c['turnover_window_pct']}% | 口径 {m['adjust']}"
        + (f" | 降级 {m['degraded']}" if m.get("degraded") else "")
        + (f" | 标记 {m['notes']}" if m.get("notes") else ""),
    ]
    return "\n".join(lines)


def render_batch(items: list) -> str:
    head = f"{'代码':<10}{'现价':>9}{'获利盘':>8}{'套牢盘':>8}{'需反弹':>8}{'墙厚':>7}  档位"
    lines = [head, "-" * len(head)]
    failed = 0
    for it in items:
        if it.get("error"):
            failed += 1
            lines.append(f"{it['code']:<10}  取数失败: {it['error']}")
            continue
        lines.append(
            f"{it['code']:<10}{it['price']:>9}{it['profit_ratio']:>8}{it['trapped_ratio']:>8}"
            f"{_num(it['rebound_to_main_pct'], '>8')}{_num(it['wall_mass_pct'], '>7')}  {it['tier']}"
        )
    if failed:
        lines.append(f"⚠ {failed} 只取数失败，未参与排序（见上）")
    return "\n".join(lines)


def main():
    from common.cache import cleanup_tmp_files

    cleanup_tmp_files()

    parser = create_parser(description="成本分布（筹码分布）分析")
    parser.add_argument("code", nargs="?", help="股票代码（如 sh600989）")
    parser.add_argument("--codes", help="批量代码，逗号分隔（如 sh600989,sz300274）")
    parser.add_argument("--pool", help="板块池名（逗号分隔可多选，如 军工,半导体）")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW, help="回看窗口，默认 250")
    parser.add_argument("--bins", type=int, default=DEFAULT_BINS, help="价格分档数，默认 240")
    parser.add_argument("--tier", help="按档位筛选，逗号分隔（筹码在脚下/上方有墙/深度套牢）")
    parser.add_argument("--min-profit", type=float, help="仅保留获利盘 ≥ 该值的标的（%%）")
    parser.add_argument("--max-rebound", type=float, help="仅保留需反弹 ≤ 该值的标的（%%）")
    parser.add_argument("--limit", type=int, help="最多输出 N 条")
    parser.add_argument(
        "--sort",
        choices=sorted(_SORT_KEYS),
        default="trapped",
        help="批量排序键：trapped/rebound/wall/profit（默认 trapped）",
    )
    args = parser.parse_args()

    if args.sources:
        from fetchers import get_kline_fetchers

        print("可用 K 线数据源（筹码优先取不复权的 sina）:")
        for f in get_kline_fetchers():
            print(f"  - {f.name} (优先级 {f.priority})")
        return

    codes = _resolve_codes(args)
    if not codes:
        err("用法: chip_dist.py <code> | --codes a,b,c | --pool 军工 [-j]")

    if len(codes) == 1:
        one = analyze_one(codes[0], args.window, args.bins)
        if args.json_output:
            print(json.dumps(one, ensure_ascii=False, indent=2, default=str))
        else:
            print(render_single(one))
        return

    items = [_flat(analyze_one(c, args.window, args.bins)) for c in codes]
    items = _apply_filters(items, args)
    items.sort(key=_SORT_KEYS[args.sort])
    if args.limit and args.limit > 0:
        items = items[: args.limit]
    if args.json_output:
        print(
            json.dumps(
                {
                    "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "window": args.window,
                    "sort": args.sort,
                    "count": len(items),
                    "failed": sum(1 for it in items if it.get("error")),
                    "items": items,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
    else:
        print(render_batch(items))


if __name__ == "__main__":
    with handle_errors():
        main()
