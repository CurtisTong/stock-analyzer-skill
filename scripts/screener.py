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
import sys
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
from data import get_quote, get_quotes, get_kline, get_finance
from classifier import infer_industry
from strategies import STRATEGIES, quality_score, valuation_score, momentum_score, liquidity_score, volatility_from_closes
from strategies.thresholds import get_industry_threshold, load_industry_thresholds
from technical.core import ema
from technical.macd import macd_full as macd_features
from technical.rsi import rsi_features
from technical.volume import volume_analysis


# ---------- 数据层适配函数 ----------

def _fetch_quote_dict(code: str) -> dict:
    """获取单只行情，返回 dict（兼容旧接口）。"""
    q = get_quote(normalize_quote_code(code))
    return q.to_dict() if q else {}


def _fetch_batch_dicts(codes: list) -> list:
    """批量获取行情，返回 dict 列表。"""
    quotes = get_quotes(codes)
    return [q.to_dict() for q in quotes]


def _fetch_kline_dicts(code: str, limit: int = 240, scale: int = 30) -> list:
    """获取 K 线，返回 dict 列表。"""
    bars = get_kline(normalize_quote_code(code), scale=scale, datalen=limit)
    return [b.to_dict() for b in bars]


def _fetch_finance_dicts(code: str) -> list:
    """获取财务数据，返回 dict 列表。"""
    records = get_finance(normalize_finance_code(code))
    return [r.to_dict() for r in records]


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
            # 尝试从 sector_mapping.json 查找 BK 代码，动态拉取
            matched = _try_fetch_from_mapping(sector)
        if not matched:
            raise SystemExit(f"未在内置标的库找到板块: {sector}")
        return sorted({normalize_quote_code(c) for c in matched})

    all_codes = []
    for items in sectors.values():
        all_codes.extend(items)
    return sorted({normalize_quote_code(c) for c in all_codes})


def _try_fetch_from_mapping(sector: str) -> list[str]:
    """从 sector_mapping.json 查找板块的 BK 代码，动态拉取成分股"""
    mapping_path = DATA_DIR / "sector_mapping.json"
    if not mapping_path.exists():
        return []
    try:
        from refresh_pool import fetch_multiple_boards, build_sector_pool
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        # 模糊匹配板块名
        for name, cfg in mapping.items():
            if name.startswith("_"):
                continue
            if sector.lower() in name.lower():
                bk_codes = cfg.get("bk_codes", [])
                if not bk_codes:
                    continue
                print(f"📡 动态获取板块 '{name}' ({', '.join(bk_codes)})...", flush=True)
                stocks = fetch_multiple_boards(bk_codes)
                if stocks:
                    pool = build_sector_pool(stocks, top_n=30)
                    print(f"  获取到 {len(pool)} 只标的")
                    return pool
        return []
    except Exception as e:
        print(f"  ⚠ 动态获取失败: {e}", file=sys.stderr)
        return []


def latest_finance(code):
    records = _fetch_finance_dicts(code)
    return records[0] if records else {}


def volume_price_features(closes, volumes):
    """量价关系分析。返回 (vol_price_signal, description)。
    signal: 1=配合良好, 0=中性, -1=背离警报。

    v1.3.2：已并入 technical.volume.volume_analysis，本函数保留为薄包装以兼容旧调用。
    """
    if len(closes) < 6 or len(volumes) < 6:
        return {"signal": 0, "desc": "数据不足"}
    result = volume_analysis(closes, volumes)
    if result is None:
        return {"signal": 0, "desc": "数据不足"}
    return {"signal": result.get("volume_price_signal", 0), "desc": result.get("volume_price", "量价中性")}


def daily_features(code):
    records = _fetch_kline_dicts(code, 240, 30)
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

    # 量价关系（v1.3.2：委托给 technical.volume.volume_analysis）
    vp = volume_analysis(closes, volumes) or {}
    vol_price_signal = vp.get("volume_price_signal", 0)

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
        "closes": closes,  # 用于波动率因子计算
    }


def hard_filter(quote, fin, args):
    """硬过滤（v1.3.1 委托给 ScreeningService 业务层）。"""
    from business.screening_service import ScreeningService
    filters = {
        "min_amount": args.min_amount,
        "min_cap": args.min_cap,
        "exclude_loss": args.exclude_loss,
    }
    return ScreeningService()._hard_filter(quote, fin, filters)
    return reasons


def prefetch_finance_all(codes):
    """并发拉取所有股票的财务数据。"""
    results = {}

    def _fetch_one(code):
        # data 层已有零值缓存校验，自动跳过无效缓存
        from data import get_finance
        records = get_finance(normalize_finance_code(code))
        return code, [r.to_dict() for r in records]

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

    # 推断行业，获取行业差异化阈值
    industry = infer_industry(quote.get("name", ""), quote_code)

    parts = {
        "quality": quality_score(fin, industry),
        "valuation": valuation_score(quote, fin, industry),
        "momentum": momentum_score(features, quote),
        "liquidity": liquidity_score(quote),
        "volatility": volatility_from_closes(features.get("closes", []), industry),
    }
    weights = STRATEGIES[strategy]
    total = sum(parts.get(k, 0) * weights.get(k, 0) for k in set(parts) | set(weights) if k != "label")
    return {
        "code": quote_code,
        "name": quote.get("name", ""),
        "board": board_type(quote_code),
        "industry": industry,
        "score": round(total, 1),
        "quality": round(parts["quality"], 1),
        "valuation": round(parts["valuation"], 1),
        "momentum": round(parts["momentum"], 1),
        "liquidity": round(parts["liquidity"], 1),
        "volatility": round(parts["volatility"], 1),
        "price": quote.get("price"),
        "change_pct": quote.get("change_pct"),
        "pe": quote.get("pe"),
        "pb": quote.get("pb"),
        "roe": fin.get("roe", fin.get("ROEJQ", "-")),
        "profit_growth": fin.get("net_profit_yoy", fin.get("PARENTNETPROFITTZ", "-")),
        "ret20": round(features["ret20"], 1),
        "trend": "上升" if features["trend"] > 0 else "下降" if features["trend"] < 0 else "震荡",
        "rsi": features.get("rsi", 50),
        "macd_signal": features.get("macd_signal", 0),
        "vol_price": "配合" if features.get("vol_price_signal", 0) > 0 else "背离" if features.get("vol_price_signal", 0) < 0 else "中性",
        "rejected": rejected,
    }


def apply_portfolio_constraints(rows: list, sector_cap: float = 0.30,
                                trend_penalty: float = 0.70) -> list:
    """应用组合层面约束。

    Args:
        rows: 已排序的候选股票列表
        sector_cap: 单板块最高占比（默认 30%）
        trend_penalty: 趋势下降标的得分乘数（默认 0.70）

    Returns:
        应用约束后的列表
    """
    if not rows:
        return rows

    max_per_sector = max(1, int(len(rows) * sector_cap))
    sector_count = {}
    result = []

    for stock in rows:
        industry = stock.get("industry", "默认")

        # 板块集中度约束
        if sector_count.get(industry, 0) >= max_per_sector:
            continue

        # 趋势下降降权
        if stock.get("trend") == "下降":
            stock["score"] = round(stock["score"] * trend_penalty, 1)

        sector_count[industry] = sector_count.get(industry, 0) + 1
        result.append(stock)

    # 重新排序（降权后排名可能变化）
    result.sort(key=lambda r: r["score"], reverse=True)
    return result


def render(rows, strategy, top):
    accepted = [r for r in rows if not r["rejected"]]
    rejected = [r for r in rows if r["rejected"]]
    accepted.sort(key=lambda r: r["score"], reverse=True)

    print(f"策略: {STRATEGIES[strategy]['label']} ({strategy})")
    print(f"入选: {len(accepted)} | 剔除: {len(rejected)}")
    print()
    header = "排名 | 代码 | 名称 | 行业 | 板块 | 总分 | 质量 | 估值 | 动量 | 流动性 | PE | ROE | RSI | 20日% | 趋势 | 量价"
    print(header)
    print("-" * len(header))
    for idx, r in enumerate(accepted[:top], 1):
        macd_icon = "↑" if r.get("macd_signal", 0) > 0 else "↓" if r.get("macd_signal", 0) < 0 else "→"
        print(
            f"{idx:>2} | {r['code']:<8} | {r['name']:<8} | {r.get('industry', '默认'):<4} | {r['board']:<4} | "
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
    parser.add_argument("--no-constraints", action="store_true", help="禁用组合约束")
    parser.add_argument("--sector-cap", type=float, default=0.30, help="单板块最高占比")
    parser.add_argument("-j", "--json", action="store_true")
    args = parser.parse_args()

    codes = load_universe(args.sector, args.codes.split(",") if args.codes else None)
    quotes = _fetch_batch_dicts(codes)
    finance_cache = prefetch_finance_all(codes)
    rows = [analyze_code(q, args.strategy, args, finance_cache) for q in quotes]
    rows.sort(key=lambda r: r["score"], reverse=True)

    # 应用组合约束（除非禁用）
    if not args.no_constraints:
        rows = apply_portfolio_constraints(rows, sector_cap=args.sector_cap)

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        render(rows, args.strategy, args.top)


if __name__ == "__main__":
    main()
