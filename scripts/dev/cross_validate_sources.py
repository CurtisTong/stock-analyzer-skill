"""离线多源一致性校验：对比 baostock / 腾讯 / 东财 日线数据。

参考文档方法学：https://zhuanlan.zhihu.com/p/2067944129309446823
    "5170 只股票、93000 条记录，Baostock 和腾讯逐条对比：
     成交额 100% 一致；价格差异 0.58%，全部因前复权因子动态变化"

本脚本对指定股票列表，分别从多个源拉取最近 N 日日线，逐条对比
close / amount，输出差异率与差异分类，建立项目自己的数据质量基线。

用法:
    # 校验单只股票
    python3 scripts/dev/cross_validate_sources.py 688981

    # 校验多只（默认 5 日）
    python3 scripts/dev/cross_validate_sources.py 600519 000001 300750 --days 10

    # 输出 JSON
    python3 scripts/dev/cross_validate_sources.py 600519 --json

设计:
    - 直接调各 kline fetcher 的 fetch()，绕过 DataFetcherManager 路由，
      确保每个源都被独立调用（而非优先级高的成功就跳过）。
    - 不依赖 baostock/akshare 包安装：未安装的源自动跳过。
    - close 差异阈值默认 0.5%（前复权因子动态变化导致的正常差异范围）。
    - amount 应 100% 一致（文档结论），差异即标记异常。

⚠️ 本脚本会发起真实网络请求，不要在高频下运行。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# 确保能 import scripts 下的模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("cross_validate")

# close 差异阈值：超过此比例记为"价格差异"（前复权因子动态变化通常 <0.6%）
CLOSE_DIFF_THRESHOLD = 0.005
# amount 差异阈值：成交额应高度一致
AMOUNT_DIFF_THRESHOLD = 0.001

# 按日对齐时比对的字段：(字段名, 差异阈值, 是否允许源间不同单位)
COMPARE_FIELDS = [
    ("close", CLOSE_DIFF_THRESHOLD, False),
    ("amount", AMOUNT_DIFF_THRESHOLD, False),
]


def _fetch_from_source(
    source_name: str, code: str, datalen: int
) -> dict[str, dict] | None:
    """从指定源拉取日线，返回 {day: record} 映射。失败返回 None。

    直接实例化单个 fetcher，绕过 DataFetcherManager 路由。
    """
    records = None
    try:
        if source_name == "baostock":
            from fetchers.kline.baostock_kline import BaostockKlineFetcher

            records = BaostockKlineFetcher().fetch(code, scale=240, datalen=datalen)
        elif source_name == "tencent":
            from fetchers.kline.tencent_kline import TencentKlineFetcher

            records = TencentKlineFetcher().fetch(code, scale=240, datalen=datalen)
        elif source_name == "eastmoney":
            from fetchers.kline.eastmoney_kline import EastmoneyKlineFetcher

            records = EastmoneyKlineFetcher().fetch(code, scale=240, datalen=datalen)
        elif source_name == "sina":
            from fetchers.kline.sina_kline import SinaKlineFetcher

            records = SinaKlineFetcher().fetch(code, scale=240, datalen=datalen)
        else:
            return None
    except Exception as e:
        logger.debug("%s 拉取 %s 失败: %s", source_name, code, e)
        return None

    if not records:
        return None
    if not isinstance(records, list):
        return None
    return {r["day"]: r for r in records if r.get("day")}


def _to_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def validate_stock(code: str, datalen: int, sources: list[str] | None = None) -> dict:
    """校验单只股票的多源日线一致性。

    Returns:
        {
            "code": code,
            "sources_used": [...],
            "sources_failed": [...],
            "common_days": N,          # 多源共有的交易日数
            "close_diff_count": N,     # close 差异记录数
            "close_diff_pct": 0.xx,    # close 差异率
            "amount_diff_count": N,
            "amount_diff_pct": 0.xx,
            "diffs": [                 # 差异明细（最多 20 条）
                {"day": "...", "field": "close", "values": {...}, "max_diff_pct": 0.xx},
            ],
        }
    """
    if sources is None:
        sources = ["baostock", "tencent", "eastmoney", "sina"]

    # 各源数据：{source: {day: record}}
    data: dict[str, dict[str, dict]] = {}
    sources_used: list[str] = []
    sources_failed: list[str] = []
    for src in sources:
        d = _fetch_from_source(src, code, datalen)
        if d is not None:
            data[src] = d
            sources_used.append(src)
        else:
            sources_failed.append(src)

    result: dict = {
        "code": code,
        "sources_used": sources_used,
        "sources_failed": sources_failed,
        "common_days": 0,
        "close_diff_count": 0,
        "close_diff_pct": 0.0,
        "amount_diff_count": 0,
        "amount_diff_pct": 0.0,
        "diffs": [],
    }

    if len(data) < 2:
        result["error"] = f"可用源不足 2 个（{sources_used}），无法对比"
        return result

    # 取所有源共有的交易日
    common_days_set = set.intersection(*(set(d.keys()) for d in data.values()))
    common_days = sorted(common_days_set)
    result["common_days"] = len(common_days)
    if not common_days:
        result["error"] = "无共有交易日"
        return result

    close_diff_count = 0
    amount_diff_count = 0
    diffs: list[dict] = []

    for day in common_days:
        for field, threshold, _ in COMPARE_FIELDS:
            values = {}
            for src in sources_used:
                rec = data[src].get(day, {})
                val = _to_float(rec.get(field))
                if val > 0:
                    values[src] = val
            if len(values) < 2:
                continue
            vmax = max(values.values())
            vmin = min(values.values())
            if vmax <= 0:
                continue
            diff_pct = (vmax - vmin) / vmax
            if diff_pct > threshold:
                if field == "close":
                    close_diff_count += 1
                elif field == "amount":
                    amount_diff_count += 1
                diffs.append(
                    {
                        "day": day,
                        "field": field,
                        "values": {k: round(v, 4) for k, v in values.items()},
                        "max_diff_pct": round(diff_pct, 6),
                    }
                )

    total = len(common_days)
    result["close_diff_count"] = close_diff_count
    result["close_diff_pct"] = round(close_diff_count / total, 4) if total else 0.0
    result["amount_diff_count"] = amount_diff_count
    result["amount_diff_pct"] = round(amount_diff_count / total, 4) if total else 0.0
    result["diffs"] = diffs[:20]  # 最多保留 20 条明细
    return result


def main():
    parser = argparse.ArgumentParser(
        description="离线多源一致性校验：对比 baostock/腾讯/东财/sina 日线数据"
    )
    parser.add_argument("codes", nargs="+", help="股票代码（如 600519 688981）")
    parser.add_argument("--days", type=int, default=5, help="校验天数（默认 5）")
    parser.add_argument(
        "--sources",
        nargs="+",
        default=None,
        help="指定源（默认 baostock tencent eastmoney sina）",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    results = []
    for code in args.codes:
        # 归一化代码：补 sh/sz 前缀
        normalized = _normalize_code(code)
        r = validate_stock(normalized, args.days, args.sources)
        results.append(r)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        _print_report(results)


def _normalize_code(code: str) -> str:
    """裸代码补交易所前缀，已带前缀的原样返回。"""
    from common import normalize_quote_code

    return normalize_quote_code(code)


def _print_report(results: list[dict]):
    """打印人类可读的校验报告。"""
    print("=" * 70)
    print("📊 多源日线一致性校验报告")
    print("=" * 70)
    for r in results:
        print(f"\n【{r['code']}】")
        print(f"  可用源: {r['sources_used']}")
        if r["sources_failed"]:
            print(f"  失败源: {r['sources_failed']}")
        if "error" in r:
            print(f"  ❌ {r['error']}")
            continue
        print(f"  共有交易日: {r['common_days']}")
        print(
            f"  close 差异: {r['close_diff_count']}/{r['common_days']}"
            f" ({r['close_diff_pct'] * 100:.2f}%)"
        )
        print(
            f"  amount 差异: {r['amount_diff_count']}/{r['common_days']}"
            f" ({r['amount_diff_pct'] * 100:.2f}%)"
        )
        if r["close_diff_pct"] > 0.01:
            print("  ⚠️ close 差异率 >1%，可能存在前复权因子未同步刷新")
        if r["amount_diff_pct"] > 0.01:
            print("  ⚠️ amount 差异率 >1%，成交额不应有差异，需排查")
        if r["diffs"]:
            print("  差异明细（前 5 条）:")
            for d in r["diffs"][:5]:
                print(
                    f"    {d['day']} {d['field']}: {d['values']}"
                    f" (差异 {d['max_diff_pct'] * 100:.3f}%)"
                )
    print("\n" + "=" * 70)
    total_close = sum(r["close_diff_count"] for r in results)
    total_days = sum(r["common_days"] for r in results)
    if total_days:
        print(
            f"汇总: close 差异 {total_close}/{total_days}"
            f" ({total_close / total_days * 100:.2f}%)"
        )
    print(
        "提示: close 差异通常源于前复权因子动态变化（文档结论 0.58%），"
        "amount 应 100% 一致。"
    )


if __name__ == "__main__":
    main()
