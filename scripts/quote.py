#!/usr/bin/env python3
"""
腾讯实时行情查询。
用法:
  quote.py sh600989                       # 单只，表格输出
  quote.py sh600989,sz000807,sh518880     # 批量（≤15/批）
  quote.py @codes.txt                     # 从文件读代码
  quote.py -j sh600989                    # JSON 输出
"""
import sys
import json
from common import http_get, decode_gbk, parse_tencent_line, split_codes, batchify, normalize_quote_code, err

URL = "https://qt.gtimg.cn/q={codes}"

def fetch_batch(codes: list) -> list:
    """调用一次腾讯 API，解析返回。"""
    url = URL.format(codes=",".join(codes))
    raw = http_get(url)
    text = decode_gbk(raw)
    results = []
    for line in text.strip().split(";"):
        line = line.strip()
        if not line:
            continue
        rec = parse_tencent_line(line)
        if rec:
            results.append(rec)
    return results

def main():
    if len(sys.argv) < 2:
        err("用法: quote.py <代码|@文件> [-j]")
    args = sys.argv[1:]
    json_mode = "-j" in args
    args = [a for a in args if a != "-j"]

    codes = [normalize_quote_code(c) for c in split_codes(args[0])]
    if not codes:
        err("未提供代码")

    all_records = []
    for batch in batchify(codes, 15):
        all_records.extend(fetch_batch(batch))

    if json_mode:
        print(json.dumps(all_records, ensure_ascii=False, indent=2))
        return

    # 表格输出
    if not all_records:
        print("(无数据)")
        return
    print(f"{'代码':<10} {'名称':<10} {'现价':>8} {'涨跌%':>7} {'PE':>7} {'换手%':>6} {'市值亿':>8}")
    print("-" * 60)
    for r in all_records:
        print(f"{r['code']:<10} {r['name']:<10} {r['price']:>8} {r['change_pct']:>7} {r['pe']:>7} {r['turnover']:>6} {r['total_cap']:>8}")

if __name__ == "__main__":
    main()
