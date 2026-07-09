#!/usr/bin/env python3
"""
热度榜（活跃 Top N）。

「热度」代理指标：成交额（元）× log(1+换手率%）
  - 成交额是市场关注度的硬指标（大资金必须有成交）
  - 换手率体现「换手活跃度」（过滤冷门大市值蓝筹的伪高成交）
  - log 抑制极端值影响，避免单只巨无霸霸榜

支持两种模式：
  - 单日榜：实时成交额 × 换手率（默认）
  - 多日榜：--days N，按近 N 个交易日累计成交额排序

跨日合并：--merge N 合并最近 N 个交易日的快照
          输出在 N 日中重复出现 ≥ K 次的股票（K 默认 ⌊N/2⌋+1）

输出到 stdout + 快照文件（data/snapshots/hot_rank/YYYY-MM-DD/）。
"""

import argparse
import json
import logging
import math
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import DATA_DIR, parallel_map, atomic_write_json
from data import get_quote, get_kline
from snapshots import list_snapshots, load_snapshot

logger = logging.getLogger(__name__)

HOT_RANK_DIR = Path(DATA_DIR) / "snapshots" / "hot_rank"


def _load_all_stocks() -> list:
    """加载全市场股票池（all_stocks.json），排除北交所。"""
    path = Path(DATA_DIR) / "all_stocks.json"
    if not path.exists():
        raise SystemExit(
            f"{path} 不存在，请先运行: python3 scripts/init_pool.py --full-market"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    codes = []
    for key in ("主板沪", "主板深", "创业板", "科创板"):
        codes.extend(data.get(key, []))
    return codes


def _filter_eligible(quotes: list) -> list:
    """过滤 ST/停牌/无成交/北交所。"""
    out = []
    for q in quotes:
        name = q.name or ""
        if "ST" in name or "退" in name:
            continue
        if q.price <= 0 or q.amount <= 0 or q.turnover <= 0:
            continue
        out.append(q)
    return out


def _hot_score(amount: float, turnover: float) -> float:
    """综合热度分 = amount × log(1 + turnover)。"""
    return amount * math.log1p(max(turnover, 0))


def _fetch_quotes_batched(
    codes: list, batch: int = 600, per_timeout: int = 180
) -> list:
    """分批并行拉 quote，每批用更长的 timeout 避免大池子超时。"""

    all_quotes = []
    total = len(codes)
    for i in range(0, total, batch):
        sub = codes[i : i + batch]
        results = parallel_map(
            lambda c: get_quote(c, use_cache=True), sub, timeout=per_timeout
        )
        all_quotes.extend([q for q in results.values() if q is not None])
        print(
            f"  · {min(i + batch, total)}/{total} ({sum(1 for v in results.values() if v is not None)} 成功)",
            flush=True,
        )
    return all_quotes


def rank_today(codes: list, top: int = 100) -> list:
    """单日热度榜：实时成交额 × 换手率。"""
    print(
        f"📡 拉取 {len(codes)} 只股票实时行情（分批 600，timeout 180s/批）...",
        flush=True,
    )
    all_quotes = _fetch_quotes_batched(codes)
    eligible = _filter_eligible(all_quotes)
    print(f"✅ 有效样本: {len(eligible)} 只（已过滤 ST/停牌/无成交）", flush=True)

    for q in eligible:
        q.hot_score = _hot_score(q.amount, q.turnover)

    eligible.sort(key=lambda q: q.hot_score, reverse=True)
    return eligible[:top]


def rank_recent_days(codes: list, days: int, top: int = 100) -> list:
    """多日热度榜：粗筛 + 拉 K 线 + 近 N 日累计成交额排序。"""
    print(
        f"📊 多日榜模式: 先用单日成交额粗筛 Top {top * 3}，再算近 {days} 日累计",
        flush=True,
    )
    rough = rank_today(codes, top=top * 3)
    target_codes = [q.code for q in rough]

    print(f"📡 拉取 {len(target_codes)} 只的近 {days} 日 K 线...", flush=True)
    kline_map = parallel_map(
        lambda c: get_kline(c, scale=240, datalen=days + 2),
        target_codes,
        timeout=60,
    )

    rows = []
    for q in rough:
        bars = kline_map.get(q.code) or []
        bars = bars[-days:] if len(bars) > days else bars
        recent_amount = sum((b.amount or 0) for b in bars)
        # 退而用：单日换手率作 turnover 代理（K线无 turnover 字段）
        hot = recent_amount * math.log1p(max(q.turnover, 1))
        rows.append(
            {
                "code": q.code,
                "name": q.name,
                "price": q.price,
                "change_pct": q.change_pct,
                "amount_1d": q.amount,
                "amount_recent": recent_amount,
                "hot_score": hot,
            }
        )

    rows.sort(key=lambda r: r["hot_score"], reverse=True)
    return rows[:top]


def rank_historical(codes: list, date_str: str, top: int = 100) -> list:
    """历史某日热度榜：用 K 线 amount 排序模拟「那天」的热度榜。

    Args:
        date_str: YYYY-MM-DD 格式
    """
    target_date = datetime.strptime(date_str, "%Y-%m-%d")
    # K 线 datalen 需要足够覆盖到 date_str
    days_back = (datetime.now() - target_date).days + 5
    if days_back < 10:
        days_back = 10

    print(f"📅 历史日榜模式: {date_str} (回溯 {days_back} 个交易日)", flush=True)
    # 粗筛：先按当日成交额筛 Top 300
    rough = rank_today(codes, top=top * 3)
    target_codes = [q.code for q in rough]

    print(
        f"📡 拉取 {len(target_codes)} 只的 K 线（直调 sina fetcher 绕开 manager）...",
        flush=True,
    )
    from fetchers.kline.sina_kline import SinaKlineFetcher
    import time as _t

    fetcher = SinaKlineFetcher()
    kline_map = {}
    succ_count = 0
    for idx, code in enumerate(target_codes, 1):
        bars = None
        for attempt in range(3):
            try:
                bars = fetcher.fetch(code, scale=240, datalen=days_back + 2)
            except Exception:
                bars = None
            if bars:
                break
            _t.sleep(0.3)
        if bars:
            kline_map[code] = bars
            succ_count += 1
        if idx % 10 == 0 or idx == len(target_codes):
            print(f"  · {idx}/{len(target_codes)} ({succ_count} 成功)", flush=True)

    rows = []
    for q in rough:
        bars = kline_map.get(q.code) or []
        # 新浪 fetcher 返回的是 dict，不是 KlineBar 对象，需用键访问
        bar = next((b for b in bars if b.get("day", "") == date_str), None)
        if not bar or float(bar.get("volume", 0) or 0) <= 0:
            continue
        # 新浪 K 线 volume 单位 = 股，amount 字段为空 → 用 volume × avg_price 估算（元）
        high = float(bar.get("high", 0) or 0)
        low = float(bar.get("low", 0) or 0)
        close = float(bar.get("close", 0) or 0)
        volume = float(bar.get("volume", 0) or 0)
        avg_price = (
            (high + low) / 2
            if (high and low)
            else (close or q.price)
        )
        amount_est = volume * avg_price
        # turnover = 成交额 / 流通市值
        turnover = (
            (amount_est / (q.circulating_cap * 1e8) * 100)
            if q.circulating_cap > 0
            else 1
        )
        rows.append(
            {
                "code": q.code,
                "name": q.name,
                "price": close or q.price,
                "change_pct": float(bar.get("pct_chg", 0) or 0),
                "amount_1d": round(amount_est, 0),
                "turnover_est": round(turnover, 2),
                "hot_score": _hot_score(amount_est, turnover),
            }
        )

    rows.sort(key=lambda r: r["hot_score"], reverse=True)
    return rows[:top]


def _save_snapshot(rows: list, mode: str, days: int) -> str:
    """保存快照到 data/snapshots/hot_rank/YYYY-MM-DD/HHMMSS-<mode>.json。"""
    now = datetime.now()
    date_dir = HOT_RANK_DIR / now.strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"{mode}_d{days}" if days > 1 else mode
    path = date_dir / f"{now.strftime('%H%M%S')}-{suffix}.json"
    out_rows = []
    for r in rows:
        d = r.to_dict() if hasattr(r, "to_dict") else dict(r)
        if "hot_score" not in d:
            d["hot_score"] = r.hot_score if hasattr(r, "hot_score") else 0
        out_rows.append(d)
    payload = {
        "snapshot_type": "hot_rank",
        "mode": mode,
        "days": days,
        "generated_at": now.isoformat(timespec="seconds"),
        "rows": out_rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, payload)
    return str(path)


def _load_window_snapshots(n_days: int) -> dict:
    """加载最近 N 个交易日所有 hot_rank 快照。返回 {code: [出现次数, 最新得分]}。"""
    counter: dict[str, dict] = {}
    paths = list_snapshots(strategy="hot_rank", limit=500)
    # 收集所有日期，倒序保留最近 n_days
    dates = sorted({Path(p).parent.name for p in paths}, reverse=True)[:n_days]
    date_set = set(dates)
    for p in paths:
        if Path(p).parent.name not in date_set:
            continue
        try:
            data = load_snapshot(Path(p))
        except Exception as e:
            logger.debug("load_snapshot 失败 %s: %s", p, e)
            continue
        for row in data.get("rows", []):
            code = row.get("code")
            if not code:
                continue
            entry = counter.setdefault(
                code, {"count": 0, "name": row.get("name", ""), "latest_score": 0}
            )
            entry["count"] += 1
            entry["latest_score"] = max(entry["latest_score"], row.get("hot_score", 0))
    return counter


def merge_recent(n_days: int, min_appear: int = None) -> list:
    """合并最近 N 个交易日快照：出现次数 ≥ min_appear 的股票。"""
    counter = _load_window_snapshots(n_days)
    threshold = min_appear if min_appear is not None else max(1, n_days // 2 + 1)
    rows = [
        {
            "code": code,
            "name": v["name"],
            "appear_count": v["count"],
            "appear_ratio": round(v["count"] / n_days, 2),
            "latest_score": round(v["latest_score"], 2),
        }
        for code, v in counter.items()
        if v["count"] >= threshold
    ]
    rows.sort(key=lambda r: (r["appear_count"], r["latest_score"]), reverse=True)
    return rows


def _print_table(rows: list, cols: list, headers: list, top: int):
    """打印简洁表格。"""
    print()
    print(f"📋 热度 Top {min(len(rows), top)}")
    print(" | ".join(f"{h:>10}" for h in headers))
    print("-" * (14 * len(headers)))
    for i, r in enumerate(rows[:top], 1):
        cells = []
        for c in cols:
            v = r.get(c) if isinstance(r, dict) else getattr(r, c, "")
            if isinstance(v, float):
                if v >= 1e8:
                    cells.append(f"{v/1e8:>9.2f}亿")
                elif v >= 1e4:
                    cells.append(f"{v/1e4:>9.2f}万")
                else:
                    cells.append(f"{v:>10.2f}")
            else:
                cells.append(f"{str(v):>10}")
        print(f"{i:>3} | " + " | ".join(cells))
    print()


def main():
    ap = argparse.ArgumentParser(description="A 股热度榜（活跃 Top N）")
    ap.add_argument("-v", "--version", action="store_true")
    ap.add_argument("--top", type=int, default=100, help="输出 Top N（默认 100）")
    ap.add_argument("--days", type=int, default=1, help="N 日累计热度（默认 1=单日）")
    ap.add_argument(
        "--merge",
        type=int,
        default=0,
        metavar="N",
        help="合并最近 N 个交易日快照（出现次数≥⌊N/2⌋+1）",
    )
    ap.add_argument(
        "--min-appear", type=int, default=None, help="合并模式下最低出现次数"
    )
    ap.add_argument(
        "--historical",
        metavar="YYYY-MM-DD",
        default=None,
        help="历史某日热度榜（用 K 线回放）",
    )
    ap.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    if args.version:
        from common import __version__

        print(f"hot_rank {__version__}")
        return

    if args.merge > 0:
        rows = merge_recent(args.merge, args.min_appear)
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            return
        print(
            f"📅 合并最近 {args.merge} 个交易日快照，出现 ≥ {args.min_appear or (args.merge // 2 + 1)} 次"
        )
        _print_table(
            rows,
            cols=["code", "name", "appear_count", "appear_ratio", "latest_score"],
            headers=["#", "代码", "名称", "出现次数", "出现比例", "最新得分"],
            top=args.top,
        )
        print(f"数据时间: {datetime.now().isoformat(timespec='seconds')}")
        print("数据源: 本地 hot_rank 快照")
        return

    codes = _load_all_stocks()
    if args.historical:
        rows = rank_historical(codes, args.historical, args.top)
        path = _save_snapshot(rows, mode=f"hist_{args.historical}", days=1)
    elif args.days > 1:
        rows = rank_recent_days(codes, args.days, args.top)
        path = _save_snapshot(rows, mode="recent", days=args.days)
    else:
        rows = rank_today(codes, args.top)
        path = _save_snapshot(rows, mode="today", days=1)

    if args.json:
        out = [r.to_dict() if hasattr(r, "to_dict") else r for r in rows]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    print(f"💾 快照已保存: {path}")
    if args.historical:
        _print_table(
            rows,
            cols=[
                "code",
                "name",
                "price",
                "change_pct",
                "turnover_est",
                "amount_1d",
                "hot_score",
            ],
            headers=[
                "#",
                "代码",
                "名称",
                "收盘",
                "涨跌%",
                "换手%(估)",
                "成交额(元)",
                "热度分",
            ],
            top=args.top,
        )
    elif args.days > 1:
        _print_table(
            rows,
            cols=["code", "name", "price", "change_pct", "amount_recent", "hot_score"],
            headers=["#", "代码", "名称", "现价", "涨跌%", "近N日累计成交", "热度分"],
            top=args.top,
        )
    else:
        _print_table(
            rows,
            cols=[
                "code",
                "name",
                "price",
                "change_pct",
                "turnover",
                "amount",
                "hot_score",
            ],
            headers=[
                "#",
                "代码",
                "名称",
                "现价",
                "涨跌%",
                "换手%",
                "成交额(元)",
                "热度分",
            ],
            top=args.top,
        )
    print(f"数据时间: {datetime.now().isoformat(timespec='seconds')}")
    print("数据源: 多 fetcher 并行 (tencent/eastmoney/sina) → 实时行情")


if __name__ == "__main__":
    main()
