#!/usr/bin/env python3
"""题材概念板块数据层。

功能：
- 概念板块列表（东财 fs=m:90+t:3）
- 题材热度排序（板块间，复用 _hot_score 公式）
- 概念板内个股热度榜（复用 fetch_board_stocks）
- 看A做B套利（锚定股所在概念板块 -> 同板块B股候选）

复用：data.pool (fetch_board_stocks, API_BASE, FIELDS), hot_rank (_hot_score), common (http_get_cached, to_float)
"""

import argparse
import json
import logging
import math
import os
import sys
from pathlib import Path
from urllib.parse import urlencode

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import to_float  # noqa: E402

logger = logging.getLogger(__name__)

# 东财概念板块列表端点参数
_CONCEPT_FS = "m:90 t:3"  # m:90=板块, t:3=概念板块（t:2=行业板块）
_CONCEPT_FIELDS = "f12,f14,f2,f3,f6,f8"  # BK代码,板块名,均价,涨跌幅,成交额,换手率
_BOARD_TTL = 300  # 概念板块列表缓存 5 分钟
_AMOUNT_YI = 1e8  # 元 -> 亿


def _hot_score(amount, turnover):
    """综合热度分 = amount × log(1 + turnover)。

    复用 hot_rank._hot_score 公式（内联实现避免循环导入）。
    """
    return amount * math.log1p(max(turnover, 0))


def _get_http():
    """延迟导入 http_get_cached（避免模块加载时初始化 common 缓存）。"""
    from common import http_get_cached

    return http_get_cached


def _get_pool():
    """延迟导入 pool 模块。"""
    from data import pool

    return pool


# ═══════════════════════════════════════════════════════════════
# 概念板块列表
# ═══════════════════════════════════════════════════════════════


def fetch_concept_boards(top=0):
    """拉取东财概念板块列表。

    Args:
        top: >0 时只返回前 N 个（按涨跌幅降序）

    Returns:
        list[dict]: [{"bk_code", "name", "price", "change_pct",
                      "amount", "turnover"}]
        按 change_pct 降序。失败返回空列表。
    """
    http_get_cached = _get_http()
    api_token = os.environ.get("EASTMONEY_API_TOKEN", "")
    extra = urlencode({"ut": api_token}) if api_token else ""
    url = (
        f"https://push2.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz=500&po=1&np=1&fltt=2&invt=2&fid=f3"
        f"&fs={_CONCEPT_FS}&fields={_CONCEPT_FIELDS}" + (f"&{extra}" if extra else "")
    )
    try:
        raw = http_get_cached(url, ttl=_BOARD_TTL)
        data = json.loads(raw)
    except Exception as e:
        logger.warning("概念板块列表获取失败: %s", e)
        return []

    if not data or data.get("rc") != 0:
        return []

    diff = (data.get("data") or {}).get("diff") or []
    boards = []
    for item in diff:
        bk_code = item.get("f12", "")
        if not bk_code or not bk_code.startswith("BK"):
            continue
        boards.append(
            {
                "bk_code": bk_code,
                "name": item.get("f14", ""),
                "price": to_float(item.get("f2")),
                "change_pct": to_float(item.get("f3")),
                "amount": to_float(item.get("f6")),
                "turnover": to_float(item.get("f8")),
            }
        )

    boards.sort(key=lambda b: b["change_pct"], reverse=True)
    if top > 0:
        boards = boards[:top]
    return boards


# ═══════════════════════════════════════════════════════════════
# 题材热度排序（板块间）
# ═══════════════════════════════════════════════════════════════


def concept_hot_rank(top=20):
    """概念板块间热度排序。

    用板块级聚合 amount/turnover 直接算热度分，无需逐股拉行情。

    Returns:
        list[dict]: [{"bk_code", "name", "hot_score", "change_pct",
                      "amount_yi", "turnover"}]
        按 hot_score 降序。
    """
    boards = fetch_concept_boards()
    if not boards:
        return []

    result = []
    for b in boards:
        amt = b.get("amount", 0)
        turnover = b.get("turnover", 0)
        if amt <= 0:
            continue
        score = _hot_score(amt, turnover)
        result.append(
            {
                "bk_code": b["bk_code"],
                "name": b["name"],
                "hot_score": round(score, 0),
                "change_pct": b["change_pct"],
                "amount_yi": round(amt / _AMOUNT_YI, 1),
                "turnover": turnover,
            }
        )

    result.sort(key=lambda x: x["hot_score"], reverse=True)
    return result[:top] if top > 0 else result


# ═══════════════════════════════════════════════════════════════
# 概念板内个股热度榜
# ═══════════════════════════════════════════════════════════════


def concept_stock_rank(bk_code, top=20):
    """某概念板块内成分股热度排序。

    复用 fetch_board_stocks 拿成分股（已含 amount/turnover），
    用 _hot_score 公式算个股热度。

    Returns:
        list[dict]: [{"code", "name", "hot_score", "change_pct",
                      "amount_yi", "turnover"}]
        按 hot_score 降序。
    """
    pool = _get_pool()
    stocks = pool.fetch_board_stocks(bk_code)
    if not stocks:
        return []

    result = []
    for s in stocks:
        amt = to_float(s.get("amount"))
        turnover = to_float(s.get("turnover"))
        if amt <= 0 or turnover <= 0:
            continue
        score = _hot_score(amt, turnover)
        result.append(
            {
                "code": s.get("code", ""),
                "name": s.get("name", ""),
                "hot_score": round(score, 0),
                "change_pct": to_float(s.get("change_pct")),
                "amount_yi": round(amt / _AMOUNT_YI, 1),
                "turnover": turnover,
            }
        )

    result.sort(key=lambda x: x["hot_score"], reverse=True)
    return result[:top] if top > 0 else result


# ═══════════════════════════════════════════════════════════════
# 看A做B套利
# ═══════════════════════════════════════════════════════════════


def find_arbitrage(anchor_code, top=5, scan_boards=30):
    """看A做B套利：找到锚定股(A)所属的概念板块，推荐同板块其他强势股(B)。

    策略前提：A 足够强（一字涨停大封单），在同板块中找 B 股套利。

    Args:
        anchor_code: 锚定股代码（如 sh600519）
        top: 每个板块返回的 B 股候选数量
        scan_boards: 扫描的热门概念板块数量

    Returns:
        list[dict]: [{"anchor_code", "concept_name", "bk_code",
                      "candidates": [{code, name, hot_score, change_pct}]}]
    """
    pool = _get_pool()

    # 归一化锚定股代码（去掉前缀匹配）
    anchor_code_clean = anchor_code
    for prefix in ("sh", "sz", "bj"):
        if anchor_code.lower().startswith(prefix):
            anchor_code_clean = anchor_code[2:]
            break

    # 拿热门概念板块
    hot_boards = concept_hot_rank(top=scan_boards)
    if not hot_boards:
        return []

    results = []
    for board in hot_boards:
        bk_code = board["bk_code"]
        stocks = pool.fetch_board_stocks(bk_code)
        if not stocks:
            continue

        # 检查锚定股是否在该板块
        anchor_in_board = any(
            s.get("code", "").endswith(anchor_code_clean) for s in stocks
        )
        if not anchor_in_board:
            continue

        # 板内热度排序，排除锚定股
        ranked = concept_stock_rank(bk_code, top=0)
        candidates = [r for r in ranked if not r["code"].endswith(anchor_code_clean)][
            :top
        ]

        results.append(
            {
                "anchor_code": anchor_code,
                "concept_name": board["name"],
                "bk_code": bk_code,
                "candidates": candidates,
            }
        )

    return results


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════


def _print_hot_rank(rankings):
    """打印题材热度排行榜。"""
    if not rankings:
        print("暂无数据")
        return
    print(
        f"{'排名':>4}  {'板块':<12} {'热度':>12} {'涨跌幅':>7} {'成交额(亿)':>10} {'换手率':>6}"
    )
    print("-" * 60)
    for i, r in enumerate(rankings, 1):
        print(
            f"{i:>4}  {r['name']:<12} {r['hot_score']:>12.0f} "
            f"{r['change_pct']:>+6.2f}% {r['amount_yi']:>10.1f} {r['turnover']:>5.2f}%"
        )


def _print_stock_rank(rankings, bk_code=""):
    """打印板内个股热度榜。"""
    if not rankings:
        print("暂无数据")
        return
    title = f"概念板块 {bk_code} 成分股热度榜" if bk_code else "成分股热度榜"
    print(f"\n{title}（共 {len(rankings)} 只）")
    print(
        f"{'排名':>4}  {'代码':<10} {'名称':<8} {'热度':>12} {'涨跌幅':>7} {'成交额(亿)':>10}"
    )
    print("-" * 60)
    for i, r in enumerate(rankings, 1):
        print(
            f"{i:>4}  {r['code']:<10} {r['name']:<8} {r['hot_score']:>12.0f} "
            f"{r['change_pct']:>+6.2f}% {r['amount_yi']:>10.1f}"
        )


def _print_arbitrage(results):
    """打印看A做B套利结果。"""
    if not results:
        print("未找到锚定股所在的概念板块")
        return
    for r in results:
        print(f"\n锚定股 {r['anchor_code']} ∈ {r['concept_name']}({r['bk_code']})")
        cands = r.get("candidates", [])
        if not cands:
            print("  无B股候选")
            continue
        print(f"  {'代码':<10} {'名称':<8} {'热度':>12} {'涨跌幅':>7}")
        print("  " + "-" * 44)
        for c in cands:
            print(
                f"  {c['code']:<10} {c['name']:<8} {c['hot_score']:>12.0f} "
                f"{c['change_pct']:>+6.2f}%"
            )


def main():
    ap = argparse.ArgumentParser(description="题材概念板块分析")
    ap.add_argument("--top", type=int, default=20, help="返回数量（默认20）")
    ap.add_argument(
        "--board", type=str, default="", help="概念板块BK代码，查看板内个股热度"
    )
    ap.add_argument("--arbitrage", type=str, default="", help="看A做B：锚定股代码")
    ap.add_argument("--scan", type=int, default=30, help="套利扫描板块数（默认30）")
    ap.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    if args.arbitrage:
        results = find_arbitrage(args.arbitrage, top=args.top, scan_boards=args.scan)
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            _print_arbitrage(results)
    elif args.board:
        rankings = concept_stock_rank(args.board, top=args.top)
        if args.json:
            print(json.dumps(rankings, ensure_ascii=False, indent=2))
        else:
            _print_stock_rank(rankings, args.board)
    else:
        rankings = concept_hot_rank(top=args.top)
        if args.json:
            print(json.dumps(rankings, ensure_ascii=False, indent=2))
        else:
            _print_hot_rank(rankings)


if __name__ == "__main__":
    main()
