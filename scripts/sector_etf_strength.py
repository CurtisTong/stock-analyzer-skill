#!/usr/bin/env python3
"""
板块 ETF 横向强度对比 + 个股相对位置（RPS）。

读取 scripts/data/sector_etf.csv 的 12 个板块 ETF，批量拉取实时行情，
计算每个 ETF 的当日/5日/20日涨跌幅、换手率、强度排名；并可选择对单只
股票输出"个股 vs 板块 vs 大盘"三段式对比。

用法:
  sector_etf_strength.py                        # 全板块排行榜（表格输出）
  sector_etf_strength.py sh600519               # 指定个股所在板块 vs 大盘
  sector_etf_strength.py sh600519 -j            # JSON 输出（供 SKILL 编排）
  sector_etf_strength.py -j                     # JSON 输出（全板块）

数据失败时优雅降级：
- sector_etf.csv 读不到 → 全量降级
- 单个 ETF quote 拉取失败 → 该 ETF 标记 null，不影响其他 ETF
- 个股板块反查失败 → stock_sector_compare 字段为 null
"""

import json
import sys
import argparse
import statistics
from pathlib import Path
from datetime import datetime

# 确保 scripts/ 在 import 路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

from data import get_quotes, get_kline  # noqa: E402 多源数据层
from common import parallel_map  # noqa: E402 并行拉取
from sector import _load_sector_stocks, find_sector_by_code  # noqa: E402 复用现有函数

DATA_DIR = Path(__file__).resolve().parent / "data"
SECTOR_ETF_CSV = DATA_DIR / "sector_etf.csv"


# ═══════════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════════

def _load_sector_etfs() -> list:
    """读取 sector_etf.csv，返回 [{code, name, category, bk_code}, ...]。

    Returns:
        list of dict，若文件不存在返回空 list（触发全量降级）。
    """
    if not SECTOR_ETF_CSV.exists():
        return []
    rows = []
    with open(SECTOR_ETF_CSV, encoding="utf-8") as f:
        # 跳过表头
        next(f)
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) < 3:
                continue
            code, name, category = parts[0], parts[1], parts[2]
            bk_code = parts[3] if len(parts) >= 4 and parts[3] else None
            rows.append({"code": code, "name": name, "category": category, "bk_code": bk_code})
    return rows


def _fetch_etf_quotes(codes: list) -> dict:
    """批量拉取 ETF 实时行情，code → quote dict。

    复用 scripts/data 层 get_quotes（多源自动切换）。
    单条失败不阻塞其他：返回的 dict 中失败 code 不存在。
    """
    if not codes:
        return {}
    quotes = get_quotes(codes, use_cache=True)
    out = {}
    for q in quotes:
        if q and q.has_basic_data():
            out[q.code] = {
                "code": q.code,
                "name": q.name,
                "price": q.price,
                "change_pct": q.change_pct,
                "turnover": q.turnover,
                "total_cap": q.total_cap,
                "pe": getattr(q, "pe", None),
            }
    return out


def _fetch_one_quote(code: str) -> dict | None:
    """获取单只股票（含个股 + 大盘指数）实时行情，复用 quote.py 路径。"""
    quotes = get_quotes([code], use_cache=True)
    if not quotes:
        return None
    q = quotes[0]
    if not q or not q.has_basic_data():
        return None
    return {
        "code": q.code,
        "name": q.name,
        "price": q.price,
        "change_pct": q.change_pct,
        "turnover": q.turnover,
        "total_cap": q.total_cap,
        "pe": getattr(q, "pe", None),
    }


# ═══════════════════════════════════════════════════════════════
# 计算：板块强度 + RPS
# ═══════════════════════════════════════════════════════════════

def compute_etf_strength(etfs_meta: list, etf_quotes: dict) -> list:
    """根据 ETF 实时涨跌幅排序，标记强度排名 + 强势/弱势分类。

    Args:
        etfs_meta: sector_etf.csv 加载结果
        etf_quotes: code → quote dict（缺失的 ETF 不出现在结果中，但会被标记）

    Returns:
        list of dict，按 change_pct 降序，包含 strength_rank
            / category / quadrant (强势|中性|弱势)
    """
    rows = []
    for meta in etfs_meta:
        code = meta["code"]
        q = etf_quotes.get(code)
        if not q:
            # 该 ETF 数据缺失，标记降级
            rows.append({
                "code": code,
                "name": meta["name"],
                "category": meta["category"],
                "change_pct": None,
                "turnover": None,
                "strength_rank": None,
                "quadrant": "数据缺失",
                "data_ok": False,
            })
            continue
        rows.append({
            "code": code,
            "name": meta["name"],
            "category": meta["category"],
            "change_pct": round(q["change_pct"], 2) if q.get("change_pct") is not None else None,
            "turnover": round(q["turnover"], 2) if q.get("turnover") is not None else None,
            "price": q.get("price"),
            "data_ok": True,
            "strength_rank": None,  # 排序后填
            "quadrant": None,
        })

    # 仅对 data_ok 的部分排序
    ok_rows = [r for r in rows if r["data_ok"]]
    ok_rows.sort(key=lambda r: r["change_pct"] or 0, reverse=True)
    for i, r in enumerate(ok_rows, 1):
        r["strength_rank"] = i
        # 强势 / 弱势 分位（按可用板块数划分）
        n = len(ok_rows)
        if n >= 3:
            if i <= max(1, n // 3):
                r["quadrant"] = "强势"
            elif i > n - max(1, n // 3):
                r["quadrant"] = "弱势"
            else:
                r["quadrant"] = "中性"
        else:
            r["quadrant"] = "中性"

    return rows


def _rps(stock_change: float | None, sector_change: float | None) -> float | None:
    """RPS（个股 vs 板块相对强度）= 个股涨幅 - 板块涨幅（pp 差值）。

    >0 跑赢板块，<0 跑输板块。任一缺失返回 None。
    """
    if stock_change is None or sector_change is None:
        return None
    return round(stock_change - sector_change, 2)


def _pick_index_quote(index_code: str = "sh000300") -> dict | None:
    """获取大盘指数行情做三段式对比基准。

    默认 sh000300 沪深300；可在调用处覆盖。
    """
    return _fetch_one_quote(index_code)


def build_stock_sector_compare(
    stock_code: str,
    stock_quote: dict | None,
    sector_etfs: list,
    index_quote: dict | None,
) -> dict:
    """生成单只股票的"个股 vs 板块 vs 大盘"三段式对比。

    Args:
        stock_code: 个股代码（如 sh600519）
        stock_quote: 个股实时行情（可 None）
        sector_etfs: compute_etf_strength 返回的 ETF 列表（含 quadrant）
        index_quote: 大盘指数行情（可 None）

    Returns:
        dict，含 stock_sector / rps_vs_sector / rps_vs_index / verdict
        任一字段缺失都标记为 None + degraded。
    """
    # 反查个股所属板块（基于 sector_stocks.json）
    sector_data = _load_sector_stocks()
    sectors = find_sector_by_code(stock_code, sector_data) if sector_data else []

    # 把 sector_stocks.json 粗粒度板块名映射到 sector_etf.csv 细粒度 ETF
    # 显式映射：粗粒度板块由哪个 ETF 代理（解决 "消费" vs "白酒ETF" 不匹配）
    _SECTOR_TO_ETF_PROXY = {
        "消费": "sh512690",    # 白酒 ETF（消费核心代理）
        "医药": "sh512010",    # 医药 ETF
        "半导体": "sh512480",  # 半导体 ETF
        "新能源": "sh515030",  # 新能源车 ETF
        "光伏": "sh515790",    # 光伏 ETF
        "军工": "sh512660",    # 军工 ETF
        "科技": "sh512480",    # 科技 → 半导体 ETF（最热细分）
        "机器人": None,        # 无对应 ETF（覆盖盲区）
        "PCB/AI算力": None,    # 无对应 ETF（覆盖盲区）
        "金融": "sh512800",    # 银行 ETF（金融最大子板块）
        "资源": "sh518880",    # 黄金 ETF（资源避险代理）
        "电力": None,          # 无对应 ETF（覆盖盲区）
        "石化": None,          # 无对应 ETF（覆盖盲区）
        "高股息": "sh510050",  # 上证50 ETF（高股息密集）
        "家电": None,          # 无对应 ETF（覆盖盲区）
    }

    matched_etf = None
    matched_via = None
    if sectors:
        for sec in sectors:
            proxy_code = _SECTOR_TO_ETF_PROXY.get(sec)
            if proxy_code:
                for etf in sector_etfs:
                    if etf["code"] == proxy_code and etf.get("data_ok"):
                        matched_etf = etf
                        matched_via = sec
                        break
                if matched_etf:
                    break
        # 退化方案：如果显式映射失败，回退到名称包含关系（保留模糊匹配兜底）
        if not matched_etf:
            for etf in sector_etfs:
                if not etf.get("data_ok"):
                    continue
                etf_name = etf["name"].replace("ETF", "")
                for sec in sectors:
                    if etf_name and (etf_name in sec or sec in etf_name):
                        matched_etf = etf
                        matched_via = sec
                        break
                if matched_etf:
                    break

    # 计算 RPS
    stock_change = stock_quote.get("change_pct") if stock_quote else None
    sector_change = matched_etf.get("change_pct") if matched_etf else None
    index_change = index_quote.get("change_pct") if index_quote else None

    rps_vs_sector = _rps(stock_change, sector_change)
    rps_vs_index = _rps(stock_change, index_change)

    # 生成 verdict
    verdict_parts = []
    if matched_etf:
        sec_quad = matched_etf.get("quadrant", "中性")
        sec_chg = matched_etf.get("change_pct")
        proxy_label = f"（代理: {matched_via}）" if matched_via else ""
        verdict_parts.append(
            f"所在板块{matched_via or ''}→ ETF {matched_etf['name']} {sec_chg:+.2f}%（{sec_quad}）{proxy_label}"
            if sec_chg is not None
            else f"所在板块{matched_via or ''}→ ETF {matched_etf['name']}（{sec_quad}）"
        )
    else:
        # 板块在 ETF 覆盖盲区（机器人/电力/家电等）
        if sectors:
            verdict_parts.append(f"板块 {','.join(sectors)} 无对应 ETF 代理（覆盖盲区）")
        else:
            verdict_parts.append("板块归属未知")

    if rps_vs_sector is not None:
        if rps_vs_sector > 0.5:
            verdict_parts.append(f"跑赢板块 {rps_vs_sector:+.2f}pp（相对抗跌/领涨）")
        elif rps_vs_sector < -0.5:
            verdict_parts.append(f"跑输板块 {rps_vs_sector:+.2f}pp（板块内偏弱）")
        else:
            verdict_parts.append(f"与板块基本同步（{rps_vs_sector:+.2f}pp）")

    if rps_vs_index is not None:
        if rps_vs_index > 0:
            verdict_parts.append(f"vs 大盘 {rps_vs_index:+.2f}pp")
        else:
            verdict_parts.append(f"vs 大盘 {rps_vs_index:+.2f}pp")

    data_quality = {
        "stock_ok": stock_quote is not None,
        "sector_ok": matched_etf is not None,
        "index_ok": index_quote is not None,
        "degraded_fields": [
            f for f, ok in [
                ("stock", stock_quote is not None),
                ("sector", matched_etf is not None),
                ("index", index_quote is not None),
            ] if not ok
        ],
    }

    return {
        "stock_code": stock_code,
        "stock_sectors": sectors or None,
        "matched_etf": matched_etf["code"] if matched_etf else None,
        "matched_etf_name": matched_etf["name"] if matched_etf else None,
        "stock_change_pct": round(stock_change, 2) if stock_change is not None else None,
        "sector_change_pct": round(sector_change, 2) if sector_change is not None else None,
        "index_change_pct": round(index_change, 2) if index_change is not None else None,
        "rps_vs_sector": rps_vs_sector,
        "rps_vs_index": rps_vs_index,
        "verdict": "; ".join(verdict_parts) if verdict_parts else "数据缺失",
        "data_quality": data_quality,
    }


# ═══════════════════════════════════════════════════════════════
# v2.7.0 新增：题材轮动强度（即时计算，无持久化）
# ═══════════════════════════════════════════════════════════════

def compute_rotation_strength(window: int = 5) -> dict | None:
    """N 日板块轮动强度（即时计算，无持久化层）。

    算法：
    1. 拉 13 个 ETF 各 datalen=window+1 的日 K 线（parallel_map 并行）
    2. 算每个 ETF "当日涨跌幅" = close[-1]/close[-2] - 1
    3. 算每个 ETF "N 日累计涨跌幅" = close[-1]/close[-(N+1)] - 1
    4. 分别排名（降序），计算位次差 rank_1d - rank_Nd（正=位次上升）
    5. 轮动强度 = 平均|位次差| + 位次差标准差

    Args:
        window: 累计涨跌幅窗口（默认 5 日）

    Returns:
        dict:
          {
            "window": 5,
            "etfs": [{code, name, change_1d_pct, change_Nd_pct,
                      rank_1d, rank_Nd, rank_delta}],
            "rotation_strength": 2.3,   # 平均|位次差|（0=无轮动, >3=剧烈）
            "rotation_std": 1.8,
            "biggest_risers": [[code, name, delta], ...],  # 位次上升 top 3
            "biggest_fallers": [[code, name, delta], ...],
            "interpretation": "...",
            "data_quality": {"degraded_fields": [...]}
          }
        全部失败 -> 返回 None。
    """
    etfs_meta = _load_sector_etfs()
    if not etfs_meta:
        return None

    # 并行拉 13 个 ETF 的 K 线（datalen=window+1，需 window+1 根算 N 日涨幅）
    etf_codes = [e["code"] for e in etfs_meta]
    kline_results = parallel_map(
        lambda c: get_kline(c, scale=240, datalen=window + 1),
        etf_codes,
        timeout=30,
    )

    # 算每个 ETF 的当日 + N 日涨跌幅
    rows = []
    degraded = []
    for meta in etfs_meta:
        code = meta["code"]
        klines = kline_results.get(code)
        if not klines or len(klines) < 2:
            degraded.append(f"rotation.{code}")
            continue
        closes = [k.close for k in klines if k.close > 0]
        if len(closes) < 2:
            degraded.append(f"rotation.{code}")
            continue

        # 当日涨跌幅（%）
        change_1d = (closes[-1] / closes[-2] - 1) * 100 if closes[-2] > 0 else None
        # N 日累计涨跌幅（%）：需要 window+1 根
        if len(closes) >= window + 1 and closes[-(window + 1)] > 0:
            change_nd = (closes[-1] / closes[-(window + 1)] - 1) * 100
        else:
            change_nd = None

        if change_1d is None or change_nd is None:
            degraded.append(f"rotation.{code}")
            continue

        rows.append({
            "code": code,
            "name": meta["name"],
            "category": meta["category"],
            "change_1d_pct": round(change_1d, 2),
            "change_nd_pct": round(change_nd, 2),
        })

    if not rows:
        return None

    # 排名（降序，1=最强）
    sorted_1d = sorted(rows, key=lambda r: r["change_1d_pct"], reverse=True)
    sorted_nd = sorted(rows, key=lambda r: r["change_nd_pct"], reverse=True)
    rank_1d_map = {r["code"]: i + 1 for i, r in enumerate(sorted_1d)}
    rank_nd_map = {r["code"]: i + 1 for i, r in enumerate(sorted_nd)}

    for r in rows:
        r["rank_1d"] = rank_1d_map[r["code"]]
        r["rank_nd"] = rank_nd_map[r["code"]]
        # rank_delta 正=位次上升（当日比 N 日强），负=位次下降
        r["rank_delta"] = r["rank_nd"] - r["rank_1d"]

    # 轮动强度 = 平均|位次差|
    abs_deltas = [abs(r["rank_delta"]) for r in rows]
    rotation_strength = round(statistics.mean(abs_deltas), 2) if abs_deltas else 0
    rotation_std = round(statistics.stdev(abs_deltas), 2) if len(abs_deltas) >= 2 else 0

    # 位次上升 / 下降 top 3
    risers = sorted(rows, key=lambda r: r["rank_delta"])[:3]  # rank_delta 最小（负最多）= 上升最多
    fallers = sorted(rows, key=lambda r: r["rank_delta"], reverse=True)[:3]
    biggest_risers = [
        [r["code"], r["name"], r["rank_delta"]] for r in risers if r["rank_delta"] < 0
    ]
    biggest_fallers = [
        [r["code"], r["name"], r["rank_delta"]] for r in fallers if r["rank_delta"] > 0
    ]

    interpretation = _interpret_rotation(rotation_strength, biggest_risers, biggest_fallers)

    return {
        "window": window,
        "etfs": rows,
        "rotation_strength": rotation_strength,
        "rotation_std": rotation_std,
        "biggest_risers": biggest_risers,
        "biggest_fallers": biggest_fallers,
        "interpretation": interpretation,
        "data_quality": {"degraded_fields": degraded},
    }


def _interpret_rotation(strength: float, risers: list, fallers: list) -> str:
    """轮动强度解读。"""
    if strength < 1.0:
        return "低轮动（板块排名稳定，趋势延续）"
    if strength < 2.5:
        return "中度轮动（板块间有切换，但主线未变）"
    return "剧烈轮动（板块排名大幅变化，主线切换中）"


# ═══════════════════════════════════════════════════════════════
# 顶层编排
# ═══════════════════════════════════════════════════════════════

def analyze(stock_code: str | None = None, fetch_index: bool = True) -> dict:
    """一次性返回所有数据，供 SKILL 直接消费。

    Args:
        stock_code: 可选。若提供，额外输出 stock_sector_compare。
        fetch_index: 是否拉取大盘指数（用于三段式对比）。technical 模式可关。

    Returns:
        dict:
            {
              "as_of": ISO8601,
              "etfs": [...],
              "strong_sectors": [code, ...],   # top 3
              "weak_sectors": [code, ...],     # bottom 3
              "stock_sector_compare": {...} | None,
              "data_quality": {...}
            }
    """
    as_of = datetime.now().isoformat(timespec="seconds")

    # 1. 加载 ETF 元数据
    etfs_meta = _load_sector_etfs()
    if not etfs_meta:
        return {
            "as_of": as_of,
            "etfs": [],
            "strong_sectors": [],
            "weak_sectors": [],
            "stock_sector_compare": None,
            "data_quality": {
                "etf_csv_ok": False,
                "degraded_fields": ["etf_csv"],
            },
            "error": "sector_etf.csv 缺失或为空",
        }

    # 2. 批量拉取 ETF 行情
    etf_codes = [e["code"] for e in etfs_meta]
    etf_quotes = _fetch_etf_quotes(etf_codes)

    # 3. 计算强度 + 排序
    etfs = compute_etf_strength(etfs_meta, etf_quotes)

    # 4. 强势 / 弱势 板块
    ok_etfs = [e for e in etfs if e.get("data_ok")]
    ok_sorted = sorted(ok_etfs, key=lambda r: r["change_pct"] or 0, reverse=True)
    strong = [r["code"] for r in ok_sorted[:3]]
    weak = [r["code"] for r in ok_sorted[-3:]] if len(ok_sorted) >= 3 else []

    # 5. 个股 vs 板块 vs 大盘（可选）
    stock_compare = None
    index_quote = None
    if stock_code:
        stock_quote = _fetch_one_quote(stock_code)
        if fetch_index:
            index_quote = _pick_index_quote("sh000300")
        stock_compare = build_stock_sector_compare(
            stock_code, stock_quote, etfs, index_quote
        )

    # 6. 数据质量汇总
    degraded = []
    if not etfs_meta:
        degraded.append("etf_csv")
    if not ok_etfs:
        degraded.append("etf_quotes")
    if stock_code and (stock_compare and not stock_compare["data_quality"]["stock_ok"]):
        degraded.append("stock")
    if stock_code and fetch_index and not index_quote:
        degraded.append("index")

    return {
        "as_of": as_of,
        "etfs": etfs,
        "strong_sectors": strong,
        "weak_sectors": weak,
        "stock_sector_compare": stock_compare,
        "data_quality": {
            "etf_csv_ok": bool(etfs_meta),
            "etf_quotes_ok": bool(ok_etfs),
            "etf_ok_count": len(ok_etfs),
            "etf_total_count": len(etfs_meta),
            "degraded_fields": degraded,
        },
    }


# ═══════════════════════════════════════════════════════════════
# CLI 输出
# ═══════════════════════════════════════════════════════════════

def _print_table(payload: dict) -> None:
    """人类可读的表格输出。"""
    as_of = payload["as_of"]
    etfs = payload["etfs"]
    strong = payload["strong_sectors"]
    weak = payload["weak_sectors"]
    compare = payload["stock_sector_compare"]

    print(f"📊 板块 ETF 横向强度对比  (as_of {as_of})")
    print("=" * 78)
    print(f"{'排名':<4} {'代码':<10} {'名称':<14} {'类别':<6} {'涨跌%':>7} {'换手%':>6}  强度")
    print("-" * 78)
    for r in etfs:
        rank = r["strength_rank"] if r["strength_rank"] else "-"
        chg = f"{r['change_pct']:+.2f}" if r["change_pct"] is not None else "N/A"
        tov = f"{r['turnover']:.2f}" if r["turnover"] is not None else "N/A"
        print(
            f"{rank:<4} {r['code']:<10} {r['name']:<14} {r['category']:<6} "
            f"{chg:>7} {tov:>6}  {r['quadrant']}"
        )

    if strong:
        print(f"\n🔥 强势板块 (top 3): {', '.join(strong)}")
    if weak:
        print(f"💀 弱势板块 (bottom 3): {', '.join(weak)}")

    if compare:
        print("\n" + "=" * 78)
        print(f"🎯 个股 vs 板块 vs 大盘 ({compare['stock_code']})")
        print(f"  所属板块    : {compare['stock_sectors'] or '未知'}")
        if compare["matched_etf"]:
            print(f"  匹配 ETF    : {compare['matched_etf']} {compare['matched_etf_name']}")
        print(f"  个股涨跌    : {compare['stock_change_pct']:+.2f}%"
              if compare["stock_change_pct"] is not None else "  个股涨跌    : N/A")
        print(f"  所在板块涨跌: {compare['sector_change_pct']:+.2f}%"
              if compare["sector_change_pct"] is not None else "  所在板块涨跌: N/A")
        print(f"  沪深300涨跌 : {compare['index_change_pct']:+.2f}%"
              if compare["index_change_pct"] is not None else "  沪深300涨跌 : N/A")
        if compare["rps_vs_sector"] is not None:
            print(f"  RPS vs 板块 : {compare['rps_vs_sector']:+.2f}pp")
        if compare["rps_vs_index"] is not None:
            print(f"  RPS vs 大盘 : {compare['rps_vs_index']:+.2f}pp")
        print(f"  结论        : {compare['verdict']}")

        dq = compare["data_quality"]
        if dq["degraded_fields"]:
            print(f"  ⚠️  降级字段 : {', '.join(dq['degraded_fields'])}")

    dq = payload["data_quality"]
    if dq["degraded_fields"]:
        print(f"\n⚠️  数据降级: {', '.join(dq['degraded_fields'])}")
    print(f"📊 数据源: sector_etf.csv ({dq['etf_ok_count']}/{dq['etf_total_count']} 个 ETF 成功)")


def main():
    parser = argparse.ArgumentParser(description="板块 ETF 横向强度对比 + 个股 RPS")
    parser.add_argument("stock_code", nargs="?", help="股票代码（如 sh600519），可选")
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    parser.add_argument("--no-index", action="store_true", help="跳过大盘指数拉取")
    args = parser.parse_args()

    payload = analyze(
        stock_code=args.stock_code,
        fetch_index=not args.no_index,
    )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_table(payload)


if __name__ == "__main__":
    main()
