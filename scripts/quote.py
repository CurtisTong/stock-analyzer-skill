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
from common import (http_get, decode_gbk, parse_tencent_line, parse_sina_quote_line,
                    split_codes, batchify, normalize_quote_code, parallel_map, err,
                    cache_key_for_stock, cache_get, cache_set, BaseFetcher, DataFetcherManager)

TENCENT_URL = "https://qt.gtimg.cn/q={codes}"
SINA_URL = "https://hq.sinajs.cn/list={codes}"


# ---------- 数据源策略 ----------

class TencentQuoteFetcher(BaseFetcher):
    """腾讯行情数据源。"""

    def __init__(self):
        super().__init__("tencent_quote", priority=10)

    def fetch(self, code: str, **kwargs) -> dict | None:
        url = TENCENT_URL.format(codes=code)
        raw = http_get(url)
        text = decode_gbk(raw)
        for line in text.strip().split(";"):
            line = line.strip()
            if not line:
                continue
            rec = parse_tencent_line(line)
            if rec:
                return rec
        return None


class SinaQuoteFetcher(BaseFetcher):
    """新浪行情数据源。"""

    def __init__(self):
        super().__init__("sina_quote", priority=5)

    def fetch(self, code: str, **kwargs) -> dict | None:
        import urllib.request
        url = SINA_URL.format(codes=code)
        req = urllib.request.Request(url, headers={
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read()
        text = raw.decode("gbk", errors="replace")
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            rec = parse_sina_quote_line(line)
            if rec:
                return rec
        return None


# 策略管理器
quote_manager = DataFetcherManager([
    TencentQuoteFetcher(),
    SinaQuoteFetcher(),
])




def fetch_batch(codes: list, use_cache: bool = True) -> list:
    """批量获取行情，支持缓存和自动故障切换。"""
    if use_cache:
        cached_results = []
        uncached_codes = []
        for code in codes:
            key = cache_key_for_stock("quote", code)
            cached = cache_get(key, ttl_seconds=900)  # 15 分钟
            if cached is not None:
                try:
                    cached_results.append(json.loads(cached))
                except json.JSONDecodeError:
                    uncached_codes.append(code)
            else:
                uncached_codes.append(code)

        if not uncached_codes:
            return cached_results
        codes_to_fetch = uncached_codes
    else:
        codes_to_fetch = codes
        cached_results = []

    # 使用策略管理器获取数据
    results = []
    for code in codes_to_fetch:
        rec = quote_manager.fetch(code)
        if rec:
            results.append(rec)

    # 写入缓存
    if use_cache:
        for rec in results:
            key = cache_key_for_stock("quote", rec["code"])
            cache_set(key, json.dumps(rec, ensure_ascii=False).encode())

    return cached_results + results

def main():
    if len(sys.argv) < 2:
        err("用法: quote.py <代码|@文件> [-j]")
    args = sys.argv[1:]
    json_mode = "-j" in args
    args = [a for a in args if a != "-j"]

    codes = [normalize_quote_code(c) for c in split_codes(args[0])]
    if not codes:
        err("未提供代码")

    batches = list(batchify(codes, 15))
    if len(batches) > 1:
        # 多批次：并发执行
        results = parallel_map(lambda b: fetch_batch(b, use_cache=True), batches, max_workers=4, timeout=30)
        all_records = []
        for batch in batches:
            all_records.extend(results.get(batch, []))
    else:
        # 单批次
        all_records = fetch_batch(batches[0])

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
