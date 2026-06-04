#!/usr/bin/env python3
"""
A 股多因子选股器。
用法:
  screener.py                         # 内置核心标的池，均衡策略
  screener.py --sector 资源 --top 5
  screener.py --strategy growth_momentum --json
  screener.py --codes sh600989,sz000807,300476
"""
import argparse
import json
import statistics
from pathlib import Path

from common import (
    DATA_DIR,
    board_type,
    normalize_finance_code,
    normalize_quote_code,
    plain_code,
)
from finance import fetch as fetch_finance
from kline import fetch as fetch_kline
from quote import fetch_batch

STRATEGIES = {
    "balanced": {
        "quality": 0.32,
        "valuation": 0.25,
        "momentum": 0.23,
        "liquidity": 0.20,
        "label": "均衡精选",
    },
    "quality_value": {
        "quality": 0.42,
        "valuation": 0.32,
        "momentum": 0.10,
        "liquidity": 0.16,
        "label": "质量价值",
    },
    "growth_momentum": {
        "quality": 0.26,
        "valuation": 0.12,
        "momentum": 0.42,
        "liquidity": 0.20,
        "label": "成长动量",
    },
    "defensive": {
        "quality": 0.38,
        "valuation": 0.34,
        "momentum": 0.08,
        "liquidity": 0.20,
        "label": "防守低波",
    },
    "turning_point": {
        "quality": 0.24,
        "valuation": 0.24,
        "momentum": 0.36,
        "liquidity": 0.16,
        "label": "拐点修复",
    },
}


def to_float(value, default=0.0):
    try:
        if value in (None, "", "-"):
            return default
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def load_universe(sector=None, codes=None):
    if codes:
        return sorted({normalize_quote_code(c) for c in codes})

    path = DATA_DIR / "sector_stocks.json"
    sectors = json.loads(path.read_text(encoding="utf-8"))
    if sector:
        matched = []
        for name, items in sectors.items():
            if sector.lower() in name.lower():
                matched.extend(items)
        if not matched:
            raise SystemExit(f"未在内置标的库找到板块: {sector}")
        return sorted({normalize_quote_code(c) for c in matched})

    all_codes = []
    for items in sectors.values():
        all_codes.extend(items)
    return sorted({normalize_quote_code(c) for c in all_codes})


def latest_finance(code):
    records = fetch_finance(normalize_finance_code(code))
    return records[0] if records else {}


def daily_features(code):
    records = fetch_kline(normalize_quote_code(code), 240, 30)
    closes = [to_float(r.get("close")) for r in records if to_float(r.get("close")) > 0]
    volumes = [to_float(r.get("volume")) for r in records if to_float(r.get("volume")) > 0]
    if len(closes) < 10:
        return {"trend": 0, "ret20": 0, "ma10": 0, "ma20": 0, "volume_ratio": 1}

    last = closes[-1]
    ma10 = statistics.mean(closes[-10:])
    ma20 = statistics.mean(closes[-20:]) if len(closes) >= 20 else statistics.mean(closes)
    base = closes[-21] if len(closes) >= 21 else closes[0]
    ret20 = (last / base - 1) * 100 if base else 0
    recent_vol = statistics.mean(volumes[-5:]) if len(volumes) >= 5 else 0
    base_vol = statistics.mean(volumes[-20:-5]) if len(volumes) >= 20 else recent_vol
    volume_ratio = recent_vol / base_vol if base_vol else 1
    trend = 0
    if last > ma10 > ma20:
        trend = 1
    elif last < ma10 < ma20:
        trend = -1
    return {
        "trend": trend,
        "ret20": ret20,
        "ma10": ma10,
        "ma20": ma20,
        "volume_ratio": volume_ratio,
    }


def quality_score(fin):
    roe = to_float(fin.get("ROEJQ"))
    profit_growth = to_float(fin.get("PARENTNETPROFITTZ"))
    revenue_growth = to_float(fin.get("TOTALOPERATEREVETZ"))
    gross_margin = to_float(fin.get("XSMLL"))
    debt = to_float(fin.get("ZCFZL"))
    eps = to_float(fin.get("EPSJB"))
    cashflow = to_float(fin.get("MGJYXJJE"))

    score = 0
    score += clamp(roe / 20 * 28)
    score += clamp(profit_growth / 40 * 22)
    score += clamp(revenue_growth / 30 * 16)
    score += clamp(gross_margin / 40 * 16)
    score += clamp((70 - debt) / 70 * 12)
    if eps > 0 and cashflow > 0:
        score += clamp((cashflow / eps) * 6, 0, 6)
    return clamp(score)


def valuation_score(quote, fin):
    pe = to_float(quote.get("pe"))
    pb = to_float(quote.get("pb"))
    growth = max(to_float(fin.get("PARENTNETPROFITTZ")), 0)
    score = 0
    if 0 < pe <= 15:
        score += 38
    elif 15 < pe <= 30:
        score += 38 - (pe - 15) / 15 * 18
    elif 30 < pe <= 60:
        score += 14 - (pe - 30) / 30 * 10
    if 0 < pb <= 2:
        score += 24
    elif 2 < pb <= 5:
        score += 24 - (pb - 2) / 3 * 14
    if pe > 0 and growth > 0:
        peg = pe / growth
        if peg <= 0.8:
            score += 28
        elif peg <= 1.5:
            score += 22
        elif peg <= 2.5:
            score += 12
    score += clamp(to_float(fin.get("ROEJQ")) / 20 * 10)
    return clamp(score)


def momentum_score(features, quote):
    ret20 = features["ret20"]
    volume_ratio = features["volume_ratio"]
    turnover = to_float(quote.get("turnover"))
    change_pct = to_float(quote.get("change_pct"))

    score = 45 if features["trend"] > 0 else 22 if features["trend"] == 0 else 8
    score += clamp((ret20 + 8) / 25 * 28)
    score += clamp((volume_ratio - 0.6) / 1.4 * 16)
    score += clamp(turnover / 6 * 8)
    if abs(change_pct) >= 9.5:
        score -= 12
    return clamp(score)


def liquidity_score(quote):
    amount = to_float(quote.get("amount"))
    cap = to_float(quote.get("total_cap"))
    turnover = to_float(quote.get("turnover"))
    score = 0
    score += clamp(amount / 120000 * 42)
    score += clamp(cap / 300 * 28)
    if 0.5 <= turnover <= 8:
        score += 24
    elif 8 < turnover <= 15:
        score += 14
    else:
        score += 6
    return clamp(score)


def hard_filter(quote, fin, args):
    reasons = []
    name = quote.get("name", "")
    if "ST" in name.upper() or "*ST" in name.upper():
        reasons.append("ST风险")
    if to_float(quote.get("amount")) < args.min_amount:
        reasons.append(f"成交额<{args.min_amount:.0f}万")
    if to_float(quote.get("total_cap")) < args.min_cap:
        reasons.append(f"市值<{args.min_cap:.0f}亿")
    if args.exclude_loss and to_float(fin.get("EPSJB")) <= 0:
        reasons.append("EPS<=0")
    return reasons


def analyze_code(quote, strategy, args):
    code = quote["code"]
    quote_code = normalize_quote_code(code)
    fin = latest_finance(quote_code)
    features = daily_features(quote_code)
    rejected = hard_filter(quote, fin, args)

    parts = {
        "quality": quality_score(fin),
        "valuation": valuation_score(quote, fin),
        "momentum": momentum_score(features, quote),
        "liquidity": liquidity_score(quote),
    }
    weights = STRATEGIES[strategy]
    total = sum(parts[k] * weights[k] for k in parts)
    return {
        "code": quote_code,
        "name": quote.get("name", ""),
        "board": board_type(quote_code),
        "score": round(total, 1),
        "quality": round(parts["quality"], 1),
        "valuation": round(parts["valuation"], 1),
        "momentum": round(parts["momentum"], 1),
        "liquidity": round(parts["liquidity"], 1),
        "price": quote.get("price"),
        "change_pct": quote.get("change_pct"),
        "pe": quote.get("pe"),
        "pb": quote.get("pb"),
        "roe": fin.get("ROEJQ", "-"),
        "profit_growth": fin.get("PARENTNETPROFITTZ", "-"),
        "ret20": round(features["ret20"], 1),
        "trend": "上升" if features["trend"] > 0 else "下降" if features["trend"] < 0 else "震荡",
        "rejected": rejected,
    }


def render(rows, strategy, top):
    accepted = [r for r in rows if not r["rejected"]]
    rejected = [r for r in rows if r["rejected"]]
    accepted.sort(key=lambda r: r["score"], reverse=True)

    print(f"策略: {STRATEGIES[strategy]['label']} ({strategy})")
    print(f"入选: {len(accepted)} | 剔除: {len(rejected)}")
    print()
    print("排名 | 代码 | 名称 | 板块 | 总分 | 质量 | 估值 | 动量 | 流动性 | PE | ROE | 20日% | 趋势")
    print("-" * 116)
    for idx, r in enumerate(accepted[:top], 1):
        print(
            f"{idx:>2} | {r['code']:<8} | {r['name']:<8} | {r['board']:<4} | "
            f"{r['score']:>5} | {r['quality']:>5} | {r['valuation']:>5} | "
            f"{r['momentum']:>5} | {r['liquidity']:>6} | {r['pe']:>6} | "
            f"{str(r['roe'])[:6]:>6} | {r['ret20']:>5} | {r['trend']}"
        )

    if rejected:
        print()
        print("剔除样本:")
        for r in rejected[:10]:
            print(f"- {r['code']} {r['name']}: {', '.join(r['rejected'])}")


def main():
    parser = argparse.ArgumentParser(description="A 股多因子选股器")
    parser.add_argument("--strategy", choices=STRATEGIES.keys(), default="balanced")
    parser.add_argument("--sector", help="内置板块名称，支持模糊匹配")
    parser.add_argument("--codes", help="逗号分隔代码列表，优先于 --sector")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--min-amount", type=float, default=5000, help="最低成交额，单位万元")
    parser.add_argument("--min-cap", type=float, default=40, help="最低总市值，单位亿元")
    parser.add_argument("--exclude-loss", action="store_true", help="剔除 EPS<=0 标的")
    parser.add_argument("-j", "--json", action="store_true")
    args = parser.parse_args()

    codes = load_universe(args.sector, args.codes.split(",") if args.codes else None)
    quotes = fetch_batch(codes)
    rows = [analyze_code(q, args.strategy, args) for q in quotes]
    rows.sort(key=lambda r: r["score"], reverse=True)

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        render(rows, args.strategy, args.top)


if __name__ == "__main__":
    main()
