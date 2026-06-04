#!/usr/bin/env python3
"""
新浪 K线数据。
用法:
  kline.py sh600989                       # 日 K，30 根
  kline.py sh600989 5 48                  # 5 分钟 K，48 根
  kline.py sh600989 240 30 -j             # JSON
参数:
  symbol  sh600989 / sz000807
  scale   5=5min, 15=15min, 30=30min, 240=日 K
  datalen 10/15/30/48
"""
import sys
import json
from common import http_get, err

URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale={scale}&ma=no&datalen={datalen}"

def fetch(symbol: str, scale: int, datalen: int) -> list:
    raw = http_get(URL.format(symbol=symbol, scale=scale, datalen=datalen))
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []

def render_table(records: list) -> str:
    if not records:
        return "(无数据)"
    lines = []
    for d in records:
        lines.append(f"{d['day']} | O:{d['open']:>7} H:{d['high']:>7} L:{d['low']:>7} C:{d['close']:>7} V:{d['volume']:>12}")
    return "\n".join(lines)

def main():
    args = sys.argv[1:]
    json_mode = "-j" in args
    args = [a for a in args if a != "-j"]
    if not args:
        err("用法: kline.py <symbol> [scale=240] [datalen=30] [-j]")
    symbol = args[0]
    scale = int(args[1]) if len(args) > 1 else 240
    datalen = int(args[2]) if len(args) > 2 else 30

    records = fetch(symbol, scale, datalen)
    if json_mode:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    else:
        print(render_table(records))

if __name__ == "__main__":
    main()
