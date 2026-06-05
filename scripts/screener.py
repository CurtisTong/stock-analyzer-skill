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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from common import (
    DATA_DIR,
    board_type,
    clamp,
    normalize_finance_code,
    normalize_quote_code,
    plain_code,
    to_float,
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


def ema(prices, period):
    """计算指数移动平均。"""
    if len(prices) < period:
        return statistics.mean(prices) if prices else 0
    k = 2 / (period + 1)
    result = statistics.mean(prices[:period])
    for p in prices[period:]:
        result = p * k + result * (1 - k)
    return result


def macd_features(closes):
    """计算 MACD: DIF, DEA, MACD 柱。返回 (dif, dea, macd_bar, signal)。
    signal: 1=金叉上穿, -1=死叉下穿, 0=无信号。"""
    if len(closes) < 34:
        return None
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    dif = ema12 - ema26

    # 计算过去 ~9 日的近似 DEA 序列来检测交叉
    difs = []
    for i in range(26, len(closes) + 1):
        e12 = ema(closes[:i], 12)
        e26 = ema(closes[:i], 26)
        difs.append(e12 - e26)
    if len(difs) < 10:
        return None
    dea = ema(difs, 9)
    prev_dif = ema(closes[:-1], 12) - ema(closes[:-1], 26)
    prev_dea_vals = difs[:-1]
    prev_dea = ema(prev_dea_vals, 9) if len(prev_dea_vals) >= 9 else dea
    macd_bar = (dif - dea) * 2

    signal = 0
    if prev_dif <= prev_dea and dif > dea:
        signal = 1   # 金叉
    elif prev_dif >= prev_dea and dif < dea:
        signal = -1  # 死叉

    return {"dif": dif, "dea": dea, "macd_bar": macd_bar, "signal": signal}


def rsi_features(closes, period=14):
    """计算 RSI。"""
    if len(closes) < period + 1:
        return {"rsi": 50, "signal": 0}
    gains = []
    losses = []
    for i in range(-period, 0):
        chg = closes[i] - closes[i - 1]
        if chg >= 0:
            gains.append(chg)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(-chg)
    avg_gain = statistics.mean(gains)
    avg_loss = statistics.mean(losses)
    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - 100 / (1 + rs)

    signal = 0
    if rsi < 30:
        signal = 1   # 超卖
    elif rsi > 70:
        signal = -1  # 超买

    return {"rsi": rsi, "signal": signal}


def volume_price_features(closes, volumes):
    """量价关系分析。返回 (vol_price_signal, description)。
    signal: 1=配合良好, 0=中性, -1=背离警报。"""
    if len(closes) < 6 or len(volumes) < 6:
        return {"signal": 0, "desc": "数据不足"}

    # 近 5 日对比前 5 日
    mid = len(closes) // 2
    recent_close = closes[-mid:]
    prev_close = closes[:mid]
    recent_vol = volumes[-mid:]
    prev_vol = volumes[:mid]

    price_chg = statistics.mean(recent_close) / max(statistics.mean(prev_close), 0.01) - 1
    vol_chg = statistics.mean(recent_vol) / max(statistics.mean(prev_vol), 0.01) - 1

    # 近 3 日 vs 整体
    last3_close = closes[-3:]
    last3_vol = volumes[-3:]
    avg_close = statistics.mean(closes)
    avg_vol = statistics.mean(volumes)

    price_up = statistics.mean(last3_close) > avg_close
    vol_up = statistics.mean(last3_vol) > avg_vol

    if price_up and vol_up:
        return {"signal": 1, "desc": "放量上涨-资金介入"}
    elif not price_up and not vol_up:
        return {"signal": 1, "desc": "缩量下跌-抛压减轻"}
    elif price_up and not vol_up:
        return {"signal": -1, "desc": "缩量上涨-量价背离"}
    elif not price_up and vol_up:
        return {"signal": -1, "desc": "放量下跌-主力出货"}
    return {"signal": 0, "desc": "量价中性"}


def daily_features(code):
    records = fetch_kline(normalize_quote_code(code), 240, 30)
    closes = [to_float(r.get("close")) for r in records if to_float(r.get("close")) > 0]
    volumes = [to_float(r.get("volume")) for r in records if to_float(r.get("volume")) > 0]
    if len(closes) < 10:
        return {
            "trend": 0, "ret20": 0, "ma10": 0, "ma20": 0, "volume_ratio": 1,
            "macd_signal": 0, "rsi": 50, "rsi_signal": 0, "vol_price_signal": 0,
        }

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

    # MACD
    macd = macd_features(closes) or {"signal": 0}
    macd_signal = macd.get("signal", 0)

    # RSI
    rsi = rsi_features(closes)
    rsi_val = rsi["rsi"]
    rsi_signal = rsi["signal"]

    # 量价关系
    vp = volume_price_features(closes, volumes)
    vol_price_signal = vp["signal"]

    return {
        "trend": trend,
        "ret20": ret20,
        "ma10": ma10,
        "ma20": ma20,
        "volume_ratio": volume_ratio,
        "macd_signal": macd_signal,
        "rsi": round(rsi_val, 1),
        "rsi_signal": rsi_signal,
        "vol_price_signal": vol_price_signal,
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
    score += clamp((ret20 + 8) / 25 * 22)
    score += clamp((volume_ratio - 0.6) / 1.4 * 12)
    score += clamp(turnover / 6 * 6)

    # MACD 金叉加分，死叉扣分
    macd_signal = features.get("macd_signal", 0)
    if macd_signal > 0:
        score += 10
    elif macd_signal < 0:
        score -= 8

    # RSI 合理区间加分，过度区域扣分
    rsi = features.get("rsi", 50)
    if 30 <= rsi <= 70:
        score += 5
    elif rsi > 80:
        score -= 6
    elif rsi < 20:
        score -= 4

    # 量价配合加分
    vol_price_signal = features.get("vol_price_signal", 0)
    if vol_price_signal > 0:
        score += 8
    elif vol_price_signal < 0:
        score -= 10

    # 涨跌停附近扣分（保留原逻辑但降低权重）
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
    bd = board_type(quote.get("code", ""))

    # ST 检测：A 股 ST 标记在名称开头，用前缀匹配而非子串匹配
    upper_name = name.upper()
    if upper_name.startswith("ST") or upper_name.startswith("*ST"):
        reasons.append("ST风险")

    # 板块差异化阈值：主板 10%，科创/创业板 20%，北交所 30% 涨跌停
    board_min_amount = {
        "主板": args.min_amount,
        "创业板": args.min_amount * 0.7,
        "科创板": args.min_amount * 0.7,
        "北交所": args.min_amount * 1.5,
    }
    board_min_cap = {
        "主板": args.min_cap,
        "创业板": args.min_cap * 0.6,
        "科创板": args.min_cap * 0.6,
        "北交所": args.min_cap * 0.4,
    }
    min_amt = board_min_amount.get(bd, args.min_amount)
    min_cap = board_min_cap.get(bd, args.min_cap)

    if to_float(quote.get("amount")) < min_amt:
        reasons.append(f"成交额<{min_amt:.0f}万")
    if to_float(quote.get("total_cap")) < min_cap:
        reasons.append(f"市值<{min_cap:.0f}亿")

    change_pct = abs(to_float(quote.get("change_pct")))
    # 涨跌停过滤：T+1 下当日无法交易
    limit_ratio = {"主板": 9.5, "创业板": 19.5, "科创板": 19.5, "北交所": 29.5}
    limit = limit_ratio.get(bd, 9.5)
    if change_pct >= limit:
        reasons.append("涨跌停限制")

    if args.exclude_loss and to_float(fin.get("EPSJB")) <= 0:
        reasons.append("EPS<=0")
    return reasons


def prefetch_finance_all(codes):
    """并发拉取所有股票的财务数据。"""
    results = {}

    def _fetch_one(code):
        return code, fetch_finance(normalize_finance_code(code))

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_fetch_one, c): c for c in codes}
        for future in as_completed(futures):
            try:
                code, data = future.result()
                results[code] = data
            except Exception:
                results[futures[future]] = []
    return results


def analyze_code(quote, strategy, args, finance_cache=None):
    code = quote["code"]
    quote_code = normalize_quote_code(code)
    if finance_cache is not None:
        records = finance_cache.get(quote_code, [])
        fin = records[0] if records else {}
    else:
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
        "rsi": features.get("rsi", 50),
        "macd_signal": features.get("macd_signal", 0),
        "vol_price": "配合" if features.get("vol_price_signal", 0) > 0 else "背离" if features.get("vol_price_signal", 0) < 0 else "中性",
        "rejected": rejected,
    }


def render(rows, strategy, top):
    accepted = [r for r in rows if not r["rejected"]]
    rejected = [r for r in rows if r["rejected"]]
    accepted.sort(key=lambda r: r["score"], reverse=True)

    print(f"策略: {STRATEGIES[strategy]['label']} ({strategy})")
    print(f"入选: {len(accepted)} | 剔除: {len(rejected)}")
    print()
    header = "排名 | 代码 | 名称 | 板块 | 总分 | 质量 | 估值 | 动量 | 流动性 | PE | ROE | RSI | 20日% | 趋势 | 量价"
    print(header)
    print("-" * len(header))
    for idx, r in enumerate(accepted[:top], 1):
        macd_icon = "↑" if r.get("macd_signal", 0) > 0 else "↓" if r.get("macd_signal", 0) < 0 else "→"
        print(
            f"{idx:>2} | {r['code']:<8} | {r['name']:<8} | {r['board']:<4} | "
            f"{r['score']:>5} | {r['quality']:>5} | {r['valuation']:>5} | "
            f"{r['momentum']:>5} | {r['liquidity']:>6} | {r['pe']:>6} | "
            f"{str(r['roe'])[:6]:>6} | {r.get('rsi', 50):>4} | {r['ret20']:>5} | {r['trend']}{macd_icon} | {r.get('vol_price', '?')}"
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
    finance_cache = prefetch_finance_all(codes)
    rows = [analyze_code(q, args.strategy, args, finance_cache) for q in quotes]
    rows.sort(key=lambda r: r["score"], reverse=True)

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        render(rows, args.strategy, args.top)


if __name__ == "__main__":
    main()
