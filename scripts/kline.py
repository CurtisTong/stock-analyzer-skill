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
from common import (normalize_quote_code, err, cache_key_for_stock, cache_get, cache_set)
from fetchers import get_kline_manager, get_kline_fetchers


def fetch(symbol: str, scale: int, datalen: int, use_cache: bool = True) -> list:
    """获取 K 线数据，支持缓存和自动故障切换。"""
    manager = get_kline_manager()
    key = cache_key_for_stock("kline", symbol, scale=scale, datalen=datalen)

    if use_cache:
        cached = cache_get(key, ttl_seconds=21600)  # 6 小时
        if cached is not None:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass

    records = manager.fetch(symbol, scale=scale, datalen=datalen)
    if records is None:
        records = []

    if use_cache and records:
        cache_set(key, json.dumps(records, ensure_ascii=False).encode())

    return records


def render_table(records: list) -> str:
    if not records:
        return "(无数据)"
    lines = []
    for d in records:
        lines.append(f"{d['day']} | O:{d['open']:>7} H:{d['high']:>7} L:{d['low']:>7} C:{d['close']:>7} V:{d['volume']:>12}")
    return "\n".join(lines)


def main():
    args = sys.argv[1:]

    if "--sources" in args:
        fetchers = get_kline_fetchers()
        print("可用 K 线数据源:")
        for f in fetchers:
            print(f"  - {f.name} (优先级 {f.priority})")
        return

    json_mode = "-j" in args
    args = [a for a in args if a not in ("-j", "--sources")]
    if not args:
        err("用法: kline.py <symbol> [scale=240] [datalen=30] [-j]")
    symbol = normalize_quote_code(args[0])
    scale = int(args[1]) if len(args) > 1 else 240
    datalen = int(args[2]) if len(args) > 2 else 30

    records = fetch(symbol, scale, datalen)
    if json_mode:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    else:
        print(render_table(records))


if __name__ == "__main__":
    main()
