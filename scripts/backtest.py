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
from common import to_float, normalize_quote_code, DATA_DIR
from kline import fetch as fetch_kline
from screener import STRATEGIES


def fetch_historical_returns(code: str, days: int = 60) -> list:
    """获取历史日收益率序列。"""
    records = fetch_kline(normalize_quote_code(code), 240, days + 5)
    if not records or len(records) < 2:
        return []
    returns = []
    for i in range(1, len(records)):
        prev_close = to_float(records[i - 1].get("close"))
        curr_close = to_float(records[i].get("close"))
        if prev_close > 0:
            returns.append((curr_close - prev_close) / prev_close)
    return returns


def simulate_strategy(strategy_name: str, codes: list, top_n: int = 5,
                      holding_days: int = 5, initial_capital: float = 100000):
    """
    模拟策略收益。

    简化回测逻辑：
    1. 按策略权重对标的排序
    2. 买入 top_n 只
    3. 持有 holding_days 天后卖出
    4. 计算收益

    Args:
        strategy_name: 策略名称
        codes: 候选股票代码列表
        top_n: 买入数量
        holding_days: 持有天数
        initial_capital: 初始资金

    Returns:
        回测结果 dict
    """
    from quote import fetch_batch
    from screener import (
        quality_score, valuation_score, momentum_score,
        liquidity_score, daily_features, infer_industry,
    )

    # 获取行情数据
    quotes = fetch_batch(codes)
    if not quotes:
        return {"error": "无法获取行情数据"}

    weights = STRATEGIES[strategy_name]

    # 计算每只股票的综合得分
    scored = []
    for q in quotes:
        code = q.get("code", "")
        industry = infer_industry(q.get("name", ""), code)

        # 获取财务数据（简化：用空数据）
        fin = {}

        # 获取技术特征
        try:
            features = daily_features(normalize_quote_code(code))
        except Exception:
            features = {"trend": 0, "ret20": 0, "volume_ratio": 1,
                        "macd_signal": 0, "rsi": 50, "vol_price_signal": 0}

        parts = {
            "quality": quality_score(fin, industry),
            "valuation": valuation_score(q, fin, industry),
            "momentum": momentum_score(features, q),
            "liquidity": liquidity_score(q),
        }
        total = sum(parts[k] * weights[k] for k in parts)

        scored.append({
            "code": code,
            "name": q.get("name", ""),
            "score": round(total, 1),
            "price": to_float(q.get("price")),
        })

    # 排序选取 top_n
    scored.sort(key=lambda x: x["score"], reverse=True)
    selected = scored[:top_n]

    # 获取历史收益
    portfolio_returns = []
    for stock in selected:
        returns = fetch_historical_returns(stock["code"], holding_days)
        if returns:
            # 取最近 holding_days 天的收益
            period_return = 1.0
            for r in returns[-holding_days:]:
                period_return *= (1 + r)
            portfolio_returns.append(period_return - 1)

    if not portfolio_returns:
        return {"error": "无法计算收益"}

    # 计算组合收益（等权重）
    avg_return = sum(portfolio_returns) / len(portfolio_returns)

    return {
        "strategy": strategy_name,
        "selected": selected,
        "returns": [round(r * 100, 2) for r in portfolio_returns],
        "avg_return_pct": round(avg_return * 100, 2),
        "holding_days": holding_days,
        "top_n": top_n,
    }


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

    # 简化夏普比率（假设无风险利率 3%）
    risk_free = 3.0 / rounds  # 每轮无风险收益
    excess_returns = [r - risk_free for r in all_returns]
    if len(excess_returns) > 1:
        import statistics
        std = statistics.stdev(excess_returns)
        sharpe = (avg_return - risk_free) / std if std > 0 else 0
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
    base = STRATEGIES[strategy_name]
    base_keys = ["quality", "valuation", "momentum", "liquidity"]

    best_score = -999
    best_weights = {k: base[k] for k in base_keys}
    results = []

    # 简化：只测试 3 个档位（-5%, 不变, +5%）
    steps = [-0.05, 0, 0.05]

    print(f"  基准权重: {best_weights}", flush=True)
    base_report = run_backtest(strategy_name, codes, top_n, days, 3)
    base_score = base_report.get("sharpe_ratio", 0)
    print(f"  基准夏普: {base_score:.2f}", flush=True)

    # 网格搜索（简化版：逐维度调整）
    for key in base_keys:
        for step in steps:
            test_weights = {k: base[k] for k in base_keys}
            test_weights[key] = max(0.05, test_weights[key] + step)

            # 归一化
            total = sum(test_weights.values())
            test_weights = {k: v / total for k, v in test_weights.items()}

            # 临时修改策略权重
            original = STRATEGIES[strategy_name].copy()
            STRATEGIES[strategy_name].update(test_weights)

            report = run_backtest(strategy_name, codes, top_n, days, 3)
            score = report.get("sharpe_ratio", 0)

            # 恢复原始权重
            STRATEGIES[strategy_name].update(original)

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
