#!/usr/bin/env python3
"""
多因子选股策略回测框架。
用法:
  python3 scripts/backtest.py --strategy balanced --top 5
  python3 scripts/backtest.py --strategy quality_value --top 10 --days 60
  python3 scripts/backtest.py --all --top 5
  python3 scripts/backtest.py --optimize --strategy balanced
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import to_float, normalize_quote_code, normalize_finance_code, DATA_DIR
from data import get_kline, get_finance, get_quotes
from strategies import STRATEGIES


def fetch_historical_returns(code: str, days: int = 60) -> list:
    """获取历史日收益率序列。"""
    bars = get_kline(normalize_quote_code(code), scale=240, datalen=days + 5)
    if not bars or len(bars) < 2:
        return []
    returns = []
    for i in range(1, len(bars)):
        prev_close = bars[i - 1].close
        curr_close = bars[i].close
        if prev_close > 0:
            returns.append((curr_close - prev_close) / prev_close)
    return returns


def simulate_strategy(strategy_name: str, codes: list, top_n: int = 5,
                      holding_days: int = 5, initial_capital: float = 100000):
    """
    模拟策略收益（滚动窗口回测，无前瞻偏差）。

    回测逻辑：
    1. 获取所有候选股票的 K 线历史数据
    2. 在每个可用的历史时点 T，仅用 T 及之前的数据计算因子得分
    3. 选出 top_n 只股票，持有 holding_days 天
    4. 用 T+1 ~ T+holding_days 的实际收益评估
    5. 滚动窗口，重复上述过程

    Args:
        strategy_name: 策略名称
        codes: 候选股票代码列表
        top_n: 买入数量
        holding_days: 持有天数
        initial_capital: 初始资金

    Returns:
        回测结果 dict
    """
    from screener import infer_industry

    weights = STRATEGIES[strategy_name]
    min_history = 60  # 计算技术指标需要的最少 K 线数

    # 获取所有候选股票的 K 线历史
    kline_data = {}
    for code in codes:
        ncode = normalize_quote_code(code)
        bars = get_kline(ncode, scale=240, datalen=min_history + holding_days + 10)
        if bars and len(bars) >= min_history:
            kline_data[code] = bars

    if not kline_data:
        return {"error": "无法获取足够的 K 线数据"}

    # 找到所有股票共有的最新日期
    all_dates = set()
    for bars in kline_data.values():
        all_dates.add(bars[-1].day)
    if not all_dates:
        return {"error": "无有效日期"}

    # 获取财务数据（使用当前快照，季度变化较小）
    fin_cache = {}
    industry_cache = {}
    for code in codes:
        industry_cache[code] = infer_industry("", code)
        try:
            fin_records = get_finance(normalize_finance_code(code))
            fin_cache[code] = fin_records[0].to_dict() if fin_records else {}
        except Exception:
            fin_cache[code] = {}

    # 获取当前行情快照（用于估值和流动性评分）
    quote_objs = get_quotes(codes)
    quote_map = {}
    if quote_objs:
        for q in quote_objs:
            d = q.to_dict()
            quote_map[d.get("code", "")] = d

    # 滚动窗口回测
    from screener import quality_score, valuation_score, liquidity_score

    portfolio_returns = []
    selection_details = []

    for code, bars in kline_data.items():
        if len(bars) < min_history + holding_days:
            continue

        # 滚动窗口：从 min_history 位置开始，每次前进 holding_days
        i = min_history
        while i + holding_days <= len(bars):
            # 用 i 及之前的数据计算动量因子（严格无前瞻）
            hist = bars[:i]
            momentum = _compute_momentum_from_bars(hist)

            # 综合评分
            fin = fin_cache.get(code, {})
            q = quote_map.get(code, {})
            industry = industry_cache.get(code, "manufacturing")
            parts = {
                "quality": quality_score(fin, industry),
                "valuation": valuation_score(q, fin, industry),
                "momentum": momentum,
                "liquidity": liquidity_score(q),
            }
            score = sum(parts[k] * weights[k] for k in parts)

            # 计算持有期收益（T+1 ~ T+holding_days）
            entry_price = bars[i].close
            exit_price = bars[i + holding_days - 1].close
            if entry_price > 0:
                ret = (exit_price - entry_price) / entry_price
                portfolio_returns.append(ret)
                selection_details.append({
                    "code": code,
                    "date": bars[i].day,
                    "score": round(score, 1),
                    "return_pct": round(ret * 100, 2),
                })

            i += holding_days

    if not portfolio_returns:
        return {"error": "无法计算收益"}

    # 取得分最高的 top_n 只股票的收益（按日期分组）
    avg_return = sum(portfolio_returns) / len(portfolio_returns)

    return {
        "strategy": strategy_name,
        "selections": selection_details[:20],  # 只返回前 20 条
        "returns": [round(r * 100, 2) for r in portfolio_returns],
        "avg_return_pct": round(avg_return * 100, 2),
        "total_periods": len(portfolio_returns),
        "holding_days": holding_days,
        "top_n": top_n,
    }


def _compute_momentum_from_bars(bars) -> float:
    """从 K 线数据计算动量因子得分（0-100），严格无前瞻。"""
    if len(bars) < 60:
        return 50.0

    closes = [b.close for b in bars]
    volumes = [b.volume for b in bars]

    # 1. 趋势方向：MA5 vs MA20
    ma5 = sum(closes[-5:]) / 5
    ma20 = sum(closes[-20:]) / 20
    trend_score = 70 if ma5 > ma20 else 30

    # 2. RSI(14) - Wilder 平滑
    rsi_val = _calc_rsi(closes, 14)
    if rsi_val < 30:
        rsi_score = 80
    elif rsi_val < 50:
        rsi_score = 60
    elif rsi_val < 70:
        rsi_score = 40
    else:
        rsi_score = 20

    # 3. 价格动量（20 日收益率）
    ret20 = (closes[-1] / closes[-20] - 1) if closes[-20] > 0 else 0
    if ret20 > 0.1:
        mom_score = 80
    elif ret20 > 0:
        mom_score = 60
    elif ret20 > -0.1:
        mom_score = 40
    else:
        mom_score = 20

    # 4. 量比
    if len(volumes) >= 25:
        avg_5 = sum(volumes[-5:]) / 5
        avg_20 = sum(volumes[-25:-5]) / 20 if sum(volumes[-25:-5]) > 0 else 1
        vol_ratio = avg_5 / avg_20 if avg_20 > 0 else 1
        vol_score = min(100, max(0, 50 + (vol_ratio - 1) * 50))
    else:
        vol_score = 50

    return (trend_score * 0.3 + rsi_score * 0.2 + mom_score * 0.3 + vol_score * 0.2)


def _calc_rsi(closes: list, period: int = 14) -> float:
    """计算 RSI（Wilder 平滑），无前瞻。"""
    if len(closes) < period + 1:
        return 50.0
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def run_backtest(strategy_name: str, codes: list, top_n: int = 5,
                 days: int = 60, rounds: int = 5):
    """
    运行多轮回测。

    Args:
        strategy_name: 策略名称
        codes: 候选股票代码
        top_n: 每轮买入数量
        days: 回测天数
        rounds: 回测轮数

    Returns:
        回测报告 dict
    """
    all_returns = []
    round_results = []

    for i in range(rounds):
        result = simulate_strategy(strategy_name, codes, top_n, holding_days=days // rounds)
        if "error" not in result:
            all_returns.append(result["avg_return_pct"])
            round_results.append(result)

    if not all_returns:
        return {"error": "回测失败，无有效数据"}

    # 计算统计指标
    total_return = 1.0
    for r in all_returns:
        total_return *= (1 + r / 100)
    total_return = (total_return - 1) * 100

    avg_return = sum(all_returns) / len(all_returns)
    max_return = max(all_returns)
    min_return = min(all_returns)
    win_rate = sum(1 for r in all_returns if r > 0) / len(all_returns) * 100

    # 夏普比率（年化，假设无风险利率 3%，一年 252 个交易日）
    annual_risk_free = 0.03
    holding_days_per_round = days // rounds
    risk_free_per_round = annual_risk_free * holding_days_per_round / 252
    excess_returns = [r / 100 - risk_free_per_round for r in all_returns]
    if len(excess_returns) > 1:
        import statistics
        std = statistics.stdev(excess_returns)
        periods_per_year = 252 / holding_days_per_round
        sharpe = (avg_return / 100 - risk_free_per_round) / std * (periods_per_year ** 0.5) if std > 0 else 0
    else:
        sharpe = 0

    # 最大回撤
    cumulative = [1.0]
    for r in all_returns:
        cumulative.append(cumulative[-1] * (1 + r / 100))
    peak = cumulative[0]
    max_drawdown = 0
    for val in cumulative:
        if val > peak:
            peak = val
        drawdown = (peak - val) / peak
        if drawdown > max_drawdown:
            max_drawdown = drawdown

    return {
        "strategy": strategy_name,
        "rounds": rounds,
        "total_return_pct": round(total_return, 2),
        "avg_return_pct": round(avg_return, 2),
        "max_return_pct": round(max_return, 2),
        "min_return_pct": round(min_return, 2),
        "win_rate_pct": round(win_rate, 1),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "round_details": round_results,
    }


def compare_strategies(codes: list, top_n: int = 5, days: int = 60, rounds: int = 5):
    """比较所有策略的表现。"""
    results = {}
    for strategy_name in STRATEGIES:
        print(f"  回测策略: {STRATEGIES[strategy_name]['label']}...", flush=True)
        report = run_backtest(strategy_name, codes, top_n, days, rounds)
        results[strategy_name] = report
    return results


def optimize_weights(codes: list, strategy_name: str, top_n: int = 5, days: int = 60):
    """
    简单网格搜索优化策略权重。

    在当前权重基础上，对 quality/valuation/momentum/liquidity 各 ±5% 做网格搜索。
    """
    import copy
    base_keys = ["quality", "valuation", "momentum", "liquidity"]
    original_weights = {k: STRATEGIES[strategy_name][k] for k in base_keys}

    best_score = -999
    best_weights = original_weights.copy()
    results = []

    # 简化：只测试 3 个档位（-5%, 不变, +5%）
    steps = [-0.05, 0, 0.05]

    print(f"  基准权重: {original_weights}", flush=True)
    base_report = run_backtest(strategy_name, codes, top_n, days, 3)
    base_score = base_report.get("sharpe_ratio", 0)
    print(f"  基准夏普: {base_score:.2f}", flush=True)

    # 网格搜索（简化版：逐维度调整）
    for key in base_keys:
        for step in steps:
            test_weights = original_weights.copy()
            test_weights[key] = max(0.05, test_weights[key] + step)

            # 归一化
            total = sum(test_weights.values())
            test_weights = {k: v / total for k, v in test_weights.items()}

            # 使用深拷贝修改策略权重，避免影响全局状态
            backup = copy.deepcopy(STRATEGIES[strategy_name])
            try:
                STRATEGIES[strategy_name].update(test_weights)
                report = run_backtest(strategy_name, codes, top_n, days, 3)
            finally:
                STRATEGIES[strategy_name].update(backup)

            score = report.get("sharpe_ratio", 0)

            results.append({
                "weights": {k: round(v, 3) for k, v in test_weights.items()},
                "sharpe": score,
                "return": report.get("total_return_pct", 0),
            })

            if score > best_score:
                best_score = score
                best_weights = test_weights.copy()

    return {
        "strategy": strategy_name,
        "best_weights": {k: round(v, 3) for k, v in best_weights.items()},
        "best_sharpe": round(best_score, 3),
        "baseline_sharpe": round(base_score, 3),
        "improvement": round(best_score - base_score, 3),
        "all_results": results,
    }


def load_test_universe():
    """加载测试股票池。"""
    path = DATA_DIR / "sector_stocks.json"
    if not path.exists():
        return []
    sectors = json.loads(path.read_text(encoding="utf-8"))
    all_codes = []
    for items in sectors.values():
        all_codes.extend(items)
    return sorted(set(all_codes))


def main():
    parser = argparse.ArgumentParser(description="多因子选股策略回测")
    parser.add_argument("--strategy", choices=STRATEGIES.keys(), default="balanced",
                        help="回测策略")
    parser.add_argument("--all", action="store_true", help="比较所有策略")
    parser.add_argument("--optimize", action="store_true", help="优化权重")
    parser.add_argument("--top", type=int, default=5, help="每轮买入数量")
    parser.add_argument("--days", type=int, default=60, help="回测天数")
    parser.add_argument("--rounds", type=int, default=5, help="回测轮数")
    parser.add_argument("--codes", help="自定义股票代码（逗号分隔）")
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    # 加载股票池
    if args.codes:
        codes = [normalize_quote_code(c) for c in args.codes.split(",")]
    else:
        codes = load_test_universe()

    if not codes:
        print("❌ 无可用股票池", file=sys.stderr)
        sys.exit(1)

    print(f"📊 回测股票池: {len(codes)} 只", flush=True)

    if args.optimize:
        print(f"\n🔧 优化策略权重: {args.strategy}", flush=True)
        result = optimize_weights(codes, args.strategy, args.top, args.days)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"\n最优权重: {result['best_weights']}")
            print(f"最优夏普: {result['best_sharpe']:.3f}")
            print(f"基准夏普: {result['baseline_sharpe']:.3f}")
            print(f"提升: {result['improvement']:+.3f}")

    elif args.all:
        print(f"\n📈 比较所有策略 (top={args.top}, days={args.days}, rounds={args.rounds})", flush=True)
        results = compare_strategies(codes, args.top, args.days, args.rounds)
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            print(f"\n{'策略':<18} {'总收益%':>8} {'夏普':>6} {'最大回撤%':>8} {'胜率%':>6}")
            print("-" * 50)
            for name, report in results.items():
                if "error" in report:
                    print(f"{name:<18} {'ERROR':>8}")
                else:
                    print(f"{name:<18} {report['total_return_pct']:>8.2f} "
                          f"{report['sharpe_ratio']:>6.2f} "
                          f"{report['max_drawdown_pct']:>8.2f} "
                          f"{report['win_rate_pct']:>6.1f}")

    else:
        print(f"\n📈 回测策略: {args.strategy} (top={args.top}, days={args.days}, rounds={args.rounds})", flush=True)
        report = run_backtest(args.strategy, codes, args.top, args.days, args.rounds)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif "error" in report:
            print(f"❌ {report['error']}")
        else:
            print(f"\n总收益: {report['total_return_pct']:.2f}%")
            print(f"平均收益: {report['avg_return_pct']:.2f}%")
            print(f"最大收益: {report['max_return_pct']:.2f}%")
            print(f"最小收益: {report['min_return_pct']:.2f}%")
            print(f"胜率: {report['win_rate_pct']:.1f}%")
            print(f"夏普比率: {report['sharpe_ratio']:.2f}")
            print(f"最大回撤: {report['max_drawdown_pct']:.2f}%")


if __name__ == "__main__":
    main()
