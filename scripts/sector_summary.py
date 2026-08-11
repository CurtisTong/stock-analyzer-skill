#!/usr/bin/env python3
"""板块涨跌幅汇总 CLI（v1.20.1 新增）。

背景:
    market / sector skill 此前只能用 sector_etf.csv 内的 15 个 ETF + quote.py 拼装,
    覆盖度低且不是真实板块榜。本次会话复盘发现"东财 push2 接口被风控 + WebFetch
    JSON 解析错误"导致板块分析耗时 +10min。

设计:
    优先级 (auto 模式):
      1. akshare 同花顺板块汇总 (stock_board_industry_summary_ths) —— 主路径,
         字段全(净流入/领涨股/上涨家数等),本会话验证可用
      2. 东方财富 push2 clist 接口 —— 备选,本次会话被风控,保留兜底
      3. 失败时 data_quality.degraded_fields 标记 ["source"],不阻断

输出 schema:
    {
      "as_of": "2026-08-11T08:00:00",
      "source": "ths" | "eastmoney" | "none",
      "items": [
        {"rank": 1, "code": "BK...", "name": "医疗服务",
         "change_pct": 4.59, "lead_stock": "毕得医药", "lead_change_pct": 20.00,
         "turnover_yi": 708.44, "net_inflow_yi": 7.50,
         "up_count": 53, "down_count": 3},
        ...
      ],
      "data_quality": {"degraded_fields": [], "source": "ths"}
    }

用法:
    python3 scripts/sector_summary.py -j
    python3 scripts/sector_summary.py -j --top 30 --source ths
    python3 scripts/sector_summary.py -j --sector 医疗服务
"""

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# 允许直接 `python3 scripts/sector_summary.py` 跑（无需 PYTHONPATH）
sys.path.insert(0, str(Path(__file__).resolve().parent))

EASTMONEY_PUSH2 = "https://push2.eastmoney.com/api/qt/clist/get"
DEFAULT_TIMEOUT = 15  # 单次 HTTP 兜底秒


def _normalize_ths_row(rank: int, row) -> dict:
    """akshare 同花顺行 → 统一 schema."""
    return {
        "rank": rank,
        "code": "",  # ths 接口不暴露 BK 代码
        "name": str(row.get("板块", "")),
        "change_pct": _to_float(row.get("涨跌幅")),
        "lead_stock": str(row.get("领涨股", "")),
        "lead_change_pct": _to_float(row.get("领涨股-涨跌幅")),
        "turnover_yi": _to_float(row.get("总成交额")),
        "net_inflow_yi": _to_float(row.get("净流入")),
        "up_count": int(row.get("上涨家数", 0) or 0),
        "down_count": int(row.get("下跌家数", 0) or 0),
    }


def _normalize_eastmoney_row(rank: int, item: dict) -> dict:
    """东方财富 push2 行 → 统一 schema."""
    return {
        "rank": rank,
        "code": str(item.get("f12", "")),
        "name": str(item.get("f14", "")),
        # 东财 f3 是小数 ×100（原始 6.95 表示 6.95%），需除以 100
        "change_pct": _to_float(item.get("f3")) / 100.0 if item.get("f3") else 0.0,
        "lead_stock": str(item.get("f104", "") or ""),
        "lead_change_pct": (
            _to_float(item.get("f105")) / 100.0 if item.get("f105") else 0.0
        ),
        "turnover_yi": _to_float(item.get("f6")) / 1e8,
        "net_inflow_yi": 0.0,  # push2 不直接给板块净流入，需二次 fetch
        "up_count": 0,
        "down_count": 0,
    }


def _to_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def fetch_ths_summary(top: int = 30) -> dict:
    """主路径: akshare 同花顺板块汇总."""
    import akshare as ak  # 延迟导入,避免无 akshare 时阻塞

    df = ak.stock_board_industry_summary_ths()
    # 按涨跌幅降序排序
    df_sorted = df.sort_values("涨跌幅", ascending=False).head(top)
    items = [
        _normalize_ths_row(i + 1, row)
        for i, (_, row) in enumerate(df_sorted.iterrows())
    ]
    return {
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "ths",
        "items": items,
        "data_quality": {"degraded_fields": [], "source": "ths"},
    }


def fetch_eastmoney_summary(top: int = 30) -> dict:
    """备选路径: 东方财富 push2 clist (行业板块 m:90+t:2)."""
    socket.setdefaulttimeout(DEFAULT_TIMEOUT)
    params = (
        f"fid=f3&po=1&pz={top}&pn=1"
        f"&fs=m:90+t:2"
        f"&fields=f1,f2,f3,f4,f5,f6,f12,f14,f104,f105,f128"
    )
    url = f"{EASTMONEY_PUSH2}?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Referer": "https://quote.eastmoney.com/center/gridlist.html",
            "Accept": "application/json,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    diff = data.get("data", {})
    rows = diff if isinstance(diff, list) else diff.get("diff", [])
    items = [_normalize_eastmoney_row(i + 1, r) for i, r in enumerate(rows[:top])]
    return {
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "eastmoney",
        "items": items,
        "data_quality": {"degraded_fields": [], "source": "eastmoney"},
    }


def fetch_sector_summary(source: str = "auto", top: int = 30) -> dict:
    """入口函数: 按 source 参数返回板块数据."""
    sources_tried: list[str] = []
    errors: dict[str, str] = {}

    order = ["ths", "eastmoney"] if source == "auto" else [source]

    for src in order:
        if src == "ths":
            try:
                return fetch_ths_summary(top)
            except Exception as e:
                errors["ths"] = f"{type(e).__name__}: {e}"
                sources_tried.append("ths")
                continue
        if src == "eastmoney":
            try:
                return fetch_eastmoney_summary(top)
            except (
                urllib.error.URLError,
                socket.timeout,
                json.JSONDecodeError,
                OSError,
            ) as e:
                errors["eastmoney"] = f"{type(e).__name__}: {e}"
                sources_tried.append("eastmoney")
                continue

    # 全部失败
    return {
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "none",
        "items": [],
        "data_quality": {
            "degraded_fields": ["source"],
            "source": "none",
            "tried": sources_tried,
            "errors": errors,
        },
    }


def filter_by_name(items: list, sector_name: str) -> list:
    """按板块名模糊匹配（中文包含匹配）。"""
    if not sector_name:
        return items
    return [it for it in items if sector_name in it.get("name", "")]


def main():
    parser = argparse.ArgumentParser(description="板块涨跌幅汇总")
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    parser.add_argument(
        "--source",
        choices=["auto", "ths", "eastmoney"],
        default="auto",
        help="数据源优先级（默认 auto: ths → eastmoney）",
    )
    parser.add_argument("--top", type=int, default=30, help="输出 Top N（默认 30）")
    parser.add_argument("--sector", default="", help="按板块名过滤（模糊匹配）")
    args = parser.parse_args()

    result = fetch_sector_summary(source=args.source, top=args.top)
    if args.sector:
        result["items"] = filter_by_name(result["items"], args.sector)
        # 重排 rank
        for i, it in enumerate(result["items"], start=1):
            it["rank"] = i

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # 文本表格输出
    print(f"📊 板块涨跌幅榜 ({result['as_of']})  来源: {result['source']}")
    if result["data_quality"].get("degraded_fields"):
        print(
            f"⚠️ 数据降级: {result['data_quality']['degraded_fields']} "
            f"(尝试 {result['data_quality'].get('tried', [])})"
        )
    print(
        f"{'#':<3} {'名称':<10} {'涨跌幅%':>8} {'领涨股':<10} "
        f"{'领涨幅%':>8} {'成交(亿)':>10} {'净流入(亿)':>10} {'涨/跌':>8}"
    )
    print("-" * 80)
    for it in result["items"]:
        print(
            f"{it['rank']:<3} {it['name'][:9]:<10} {it['change_pct']:>+8.2f} "
            f"{it['lead_stock'][:9]:<10} {it['lead_change_pct']:>+8.2f} "
            f"{it['turnover_yi']:>10.1f} {it['net_inflow_yi']:>+10.1f} "
            f"{it['up_count']:>3}/{it['down_count']:<3}"
        )


if __name__ == "__main__":
    main()
