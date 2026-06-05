#!/usr/bin/env python3
"""
东方财富财务数据。
用法:
  finance.py SH600989                  # 单只，最近 4 季
  finance.py -c SH600989,SZ000807      # 批量
  finance.py -j SH600989               # JSON 输出
"""
import sys
import json
from common import http_get, cache_key_for_stock, cache_get, cache_set, EAST_MONEY_FIELDS, normalize_finance_code, parallel_map, err

URL = "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/ZYZBAjaxNew?type=0&code={code}"

def fetch(code: str, use_cache: bool = True) -> list:
    """返回最近 4 季的财务数据，支持按股票代码缓存（TTL 6 小时）。"""
    key = cache_key_for_stock("finance", code)
    if use_cache:
        cached = cache_get(key, ttl_seconds=21600)  # 6 小时
        if cached is not None:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass

    raw = http_get(URL.format(code=code))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not data or "data" not in data or not data["data"]:
        return []
    result = data["data"][:4]

    if use_cache and result:
        cache_set(key, json.dumps(result, ensure_ascii=False).encode())
    return result

def render_table(records: list) -> str:
    if not records:
        return "(无数据)"
    keys = list(EAST_MONEY_FIELDS.keys())
    lines = []
    header = " | ".join(["报告期"] + [EAST_MONEY_FIELDS[k] for k in keys])
    lines.append(header)
    lines.append("-" * len(header))
    for r in records:
        # 取日期字段（首字段）作为报告期
        period = r.get("REPORT_DATE") or r.get("NOTICE_DATE") or r.get("SECURITYCODE") or "?"
        # 兼容：尝试几个可能的日期字段
        for dk in ["REPORT_DATE", "REPORTDATETIME", "NOTICE_DATE", "DECLARE_DATE"]:
            if dk in r and r[dk]:
                period = str(r[dk])[:10]
                break
        values = [r.get(k, "-") for k in keys]
        lines.append(" | ".join([period] + [str(v)[:8] for v in values]))
    return "\n".join(lines)

def main():
    if len(sys.argv) < 2:
        err("用法: finance.py <代码> [-c codes] [-j]")
    args = sys.argv[1:]
    json_mode = "-j" in args
    args = [a for a in args if a != "-j"]
    if not args:
        err("缺少代码")

    if args[0] == "-c":
        codes = args[1].split(",")
    else:
        codes = [args[0]]

    normalized_codes = [normalize_finance_code(c) for c in codes]

    if len(normalized_codes) > 1:
        # 批量模式：并发查询
        results = parallel_map(fetch, normalized_codes, max_workers=4, timeout=30)
        all_results = {k: v for k, v in results.items() if v}
    else:
        # 单只模式
        all_results = {normalized_codes[0]: fetch(normalized_codes[0])}

    if json_mode:
        print(json.dumps(all_results, ensure_ascii=False, indent=2))
        return

    for code, records in all_results.items():
        print(f"\n=== {code} ===")
        print(render_table(records))

if __name__ == "__main__":
    main()
