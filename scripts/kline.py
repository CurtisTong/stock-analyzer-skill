#!/usr/bin/env python3
"""
K 线数据查询（多数据源自动切换）。
数据源: 新浪 → 东方财富 → 腾讯 → efinance → akshare → tushare → 通达信 → baostock → yfinance
用法:
  kline.py sh600989                       # 日 K，30 根
  kline.py sh600989 5 48                  # 5 分钟 K，48 根
  kline.py sh600989 240 30 -j             # JSON
  kline.py --sources                      # 显示可用数据源
"""
import sys
import json
import argparse
from common import normalize_quote_code, err, DataError
from data import get_kline


def fetch(symbol: str, scale: int, datalen: int, use_cache: bool = True) -> list:
    """获取 K 线数据，返回 dict 列表（兼容旧接口）。"""
    bars = get_kline(symbol, scale, datalen, use_cache=use_cache)
    return [b.to_dict() for b in bars]


def aggregate_klines(records: list, period: str = "week") -> list:
    """将日 K 线聚合为周 K 线（或月 K 线）。

    Args:
        records: 日 K 线 dict 列表，每条需含 day/open/high/low/close/volume 字段
        period: 聚合周期，"week" 按 ISO 周聚合，"month" 按月聚合

    Returns:
        聚合后的 K 线 dict 列表，包含 day/open/high/low/close/volume 字段
    """
    if not records:
        return []

    from datetime import datetime

    def _group_key(day_str: str) -> str:
        """按周期生成分组键。"""
        try:
            dt = datetime.strptime(day_str[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return day_str[:8]  # fallback: 按前8位分组
        if period == "month":
            return dt.strftime("%Y-%m")
        # week: ISO 年-周号
        iso_year, iso_week, _ = dt.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"

    groups = []
    current_key = None
    current_bars = []

    for r in records:
        day = r.get("day", "")
        key = _group_key(day)
        if key != current_key:
            if current_bars:
                groups.append(current_bars)
            current_bars = [r]
            current_key = key
        else:
            current_bars.append(r)

    # P0 fix: 最后一组必须加入，不能遗漏
    if current_bars:
        groups.append(current_bars)

    result = []
    for bars in groups:
        agg = {
            "day": bars[-1]["day"],  # 取最后一天的日期作为聚合日期
            "open": bars[0].get("open", 0),
            "high": max(b.get("high", 0) for b in bars),
            "low": min(b.get("low", float("inf")) for b in bars),
            "close": bars[-1].get("close", 0),
            "volume": sum(b.get("volume", 0) for b in bars),
        }
        result.append(agg)

    return result


def render_table(records: list) -> str:
    if not records:
        return "(无数据)"
    lines = []
    for d in records:
        lines.append(f"{d['day']} | O:{d['open']:>7} H:{d['high']:>7} L:{d['low']:>7} C:{d['close']:>7} V:{d['volume']:>12}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="K 线数据查询（多数据源自动切换）")
    parser.add_argument("symbol", nargs="?", help="股票代码（如 sh600989）")
    parser.add_argument("scale", nargs="?", type=int, default=240, help="K 线周期（240=日，5=5分钟），默认 240")
    parser.add_argument("datalen", nargs="?", type=int, default=30, help="数据条数，默认 30")
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    parser.add_argument("--sources", action="store_true", help="显示可用数据源")
    args = parser.parse_args()

    if args.sources:
        from fetchers import get_kline_fetchers
        fetchers = get_kline_fetchers()
        print("可用 K 线数据源:")
        for f in fetchers:
            print(f"  - {f.name} (优先级 {f.priority})")
        return

    if not args.symbol:
        err("用法: kline.py <symbol> [scale=240] [datalen=30] [-j|--json]")

    symbol = normalize_quote_code(args.symbol)
    records = fetch(symbol, args.scale, args.datalen)
    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    else:
        print(render_table(records))


if __name__ == "__main__":
    try:
        main()
    except DataError as e:
        sys.exit(1)
