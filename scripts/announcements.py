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
import argparse
from datetime import datetime, timedelta
from common import http_get, err, DataError, cache_key_for_stock, cache_get, cache_set
from common.utils import plain_code

ANN_URL = "https://np-anotice-stock.eastmoney.com/api/security/ann?page_size=10&page_index=1&ann_type=A&stock_list={code}&f_node=0"
# 东方财富研报 API 需要 pageNo, beginTime, qType 参数
REPORT_URL = "https://reportapi.eastmoney.com/report/list?pageSize=10&pageNo=1&code={code}&beginTime={begin_time}&endTime={end_time}&qType=0"


def fetch_announcements(code: str, use_cache: bool = True) -> list:
    """获取公告数据，支持缓存（TTL 30 分钟）。"""
    plain = plain_code(code)
    key = cache_key_for_stock("ann", plain)
    if use_cache:
        cached = cache_get(key, ttl_seconds=1800)  # 30 分钟
        if cached is not None:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass

    raw = http_get(ANN_URL.format(code=plain))
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
    plain = plain_code(code)
    key = cache_key_for_stock("report", plain)
    if use_cache:
        cached = cache_get(key, ttl_seconds=3600)  # 1 小时
        if cached is not None:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass

    # 计算时间范围：最近 1 年
    end_date = datetime.now()
    begin_date = end_date - timedelta(days=365)
    begin_time = begin_date.strftime("%Y-%m-%d")
    end_time = end_date.strftime("%Y-%m-%d")

    url = REPORT_URL.format(code=plain, begin_time=begin_time, end_time=end_time)
    raw = http_get(url)
    try:
        data = json.loads(raw)
        # API 返回 {"hits": N, "data": [...], ...} 结构
        result = data.get("data", []) if isinstance(data, dict) else []
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
        it.get("infoCode", "")  # 简化
        lines.append(f"{date} | {org} | {title}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="东方财富公告 + 研报")
    parser.add_argument("code", nargs="?", help="股票代码（如 600989）")
    parser.add_argument(
        "mode",
        nargs="?",
        default="announcements",
        choices=["announcements", "reports"],
        help="类型：announcements（公告）或 reports（研报）",
    )
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    if not args.code:
        err("用法: announcements.py <代码> [announcements|reports] [-j|--json]")

    if args.mode == "reports":
        data = fetch_reports(args.code)
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(f"\n=== 研报 {args.code} ===")
            print(render_reports(data))
    else:
        data = fetch_announcements(args.code)
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(f"\n=== 公告 {args.code} ===")
            print(render_announcements(data))


if __name__ == "__main__":
    try:
        main()
    except DataError:
        sys.exit(1)
