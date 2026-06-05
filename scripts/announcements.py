#!/usr/bin/env python3
"""
东方财富公告 + 研报。
用法:
  announcements.py 600989                  # 最新公告
  announcements.py 600989 reports          # 券商研报
  announcements.py 600989 -j               # JSON
"""
import sys
import json
from common import http_get, err, DataError, cache_key_for_stock, cache_get, cache_set

ANN_URL = "https://np-anotice-stock.eastmoney.com/api/security/ann?page_size=10&page_index=1&ann_type=A&stock_list={code}&f_node=0"
REPORT_URL = "https://reportapi.eastmoney.com/report/list?pageSize=10&code={code}"

def fetch_announcements(code: str, use_cache: bool = True) -> list:
    """获取公告数据，支持缓存（TTL 30 分钟）。"""
    key = cache_key_for_stock("ann", code)
    if use_cache:
        cached = cache_get(key, ttl_seconds=1800)  # 30 分钟
        if cached is not None:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass

    raw = http_get(ANN_URL.format(code=code))
    try:
        data = json.loads(raw)
        result = data.get("data", {}).get("list", [])
        if use_cache and result:
            cache_set(key, json.dumps(result, ensure_ascii=False).encode())
        return result
    except json.JSONDecodeError:
        return []

def fetch_reports(code: str, use_cache: bool = True) -> list:
    """获取研报数据，支持缓存（TTL 1 小时）。"""
    key = cache_key_for_stock("report", code)
    if use_cache:
        cached = cache_get(key, ttl_seconds=3600)  # 1 小时
        if cached is not None:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass

    raw = http_get(REPORT_URL.format(code=code))
    try:
        data = json.loads(raw)
        result = data if isinstance(data, list) else []
        if use_cache and result:
            cache_set(key, json.dumps(result, ensure_ascii=False).encode())
        return result
    except json.JSONDecodeError:
        return []

def render_announcements(items: list) -> str:
    if not items:
        return "(无公告)"
    lines = []
    for it in items[:10]:
        title = it.get("title", "").strip()
        date = it.get("notice_date", "")[:10] or it.get("notice_time", "")[:10]
        lines.append(f"{date} | {title}")
    return "\n".join(lines)

def render_reports(items: list) -> str:
    if not items:
        return "(无研报)"
    lines = []
    for it in items[:10]:
        title = it.get("title", "").strip()
        org = it.get("orgSName", "")
        date = it.get("publishDate", "")[:10]
        rating = it.get("infoCode", "")  # 简化
        lines.append(f"{date} | {org} | {title}")
    return "\n".join(lines)

def main():
    if len(sys.argv) < 2:
        err("用法: announcements.py <代码> [reports] [-j]")
    args = sys.argv[1:]
    json_mode = "-j" in args
    args = [a for a in args if a != "-j"]
    code = args[0]
    mode = args[1] if len(args) > 1 else "announcements"

    if mode == "reports":
        data = fetch_reports(code)
        if json_mode:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(f"\n=== 研报 {code} ===")
            print(render_reports(data))
    else:
        data = fetch_announcements(code)
        if json_mode:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(f"\n=== 公告 {code} ===")
            print(render_announcements(data))

if __name__ == "__main__":
    try:
        main()
    except DataError as e:
        sys.exit(1)
