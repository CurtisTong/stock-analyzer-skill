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
    # 追加机构一致预期小结（解决审查 #17：机构预期完全缺失）
    consensus = summarize_consensus(items)
    if consensus:
        lines.append("")
        lines.append("=== 机构一致预期 ===")
        lines.append(f"覆盖机构数: {consensus['institution_count']}")
        if consensus["target_price_avg"] > 0:
            lines.append(
                f"目标价均值: {consensus['target_price_avg']:.2f} 元"
                f"（{consensus['target_price_count']} 家给出）"
            )
        if consensus["rating_distribution"]:
            rating_str = "、".join(
                f"{k} {v}家" for k, v in consensus["rating_distribution"]
            )
            lines.append(f"评级分布: {rating_str}")
        if consensus["predict_eps_this_year"] > 0:
            lines.append(
                f"预测EPS(当年/次年): {consensus['predict_eps_this_year']:.2f}"
                f" / {consensus['predict_eps_next_year']:.2f}"
            )
        if consensus["predict_pe_this_year"] > 0:
            lines.append(
                f"预测PE(当年/次年): {consensus['predict_pe_this_year']:.2f}"
                f" / {consensus['predict_pe_next_year']:.2f}"
            )
    return "\n".join(lines)


def summarize_consensus(items: list) -> dict:
    """从研报列表聚合机构一致预期（解决审查 #17）。

    东财 reportapi 已返回目标价/评级/预测EPS/预测PE，但 render_reports 原仅提取
    标题/机构/日期，本函数补齐结构化聚合。

    Args:
        items: fetch_reports 返回的原始研报列表（含 indvAimPriceT/emRatingName/...）

    Returns:
        {
            "institution_count": int,            # 覆盖机构数
            "target_price_avg": float,           # 目标价均值（元）
            "target_price_count": int,           # 给出目标价的机构数
            "rating_distribution": list[tuple],  # [(评级, 数量), ...] 按数量降序
            "predict_eps_this_year": float,      # 预测当年EPS
            "predict_eps_next_year": float,      # 预测次年EPS
            "predict_pe_this_year": float,       # 预测当年PE
            "predict_pe_next_year": float,       # 预测次年PE
        }
    """
    if not items:
        return {}

    # 目标价：indvAimPriceT（目标价-上限）优先，回退 indvAimPriceL
    target_prices = []
    for it in items:
        tp = it.get("indvAimPriceT") or it.get("indvAimPriceL")
        if tp:
            try:
                val = float(tp)
                if val > 0:
                    target_prices.append(val)
            except (TypeError, ValueError):
                pass

    # 评级分布：emRatingName（买入/增持/中性/减持/卖出）
    ratings = {}
    for it in items:
        rating = it.get("emRatingName") or it.get("sRatingName")
        if rating:
            ratings[rating] = ratings.get(rating, 0) + 1

    # 预测EPS/PE：取最新一期研报（items[0] 通常按 publishDate 降序）
    latest = items[0] if items else {}

    def _safe_float(val):
        if not val:
            return 0.0
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    return {
        "institution_count": len(items),
        "target_price_avg": (
            sum(target_prices) / len(target_prices) if target_prices else 0.0
        ),
        "target_price_count": len(target_prices),
        "rating_distribution": sorted(
            ratings.items(), key=lambda x: -x[1]
        ),
        "predict_eps_this_year": _safe_float(latest.get("predictThisYearEps")),
        "predict_eps_next_year": _safe_float(latest.get("predictNextYearEps")),
        "predict_pe_this_year": _safe_float(latest.get("predictThisYearPe")),
        "predict_pe_next_year": _safe_float(latest.get("predictNextYearPe")),
    }


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
