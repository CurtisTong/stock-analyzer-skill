"""
回测 CLI 入口：策略比较、权重优化、命令行解析。
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import normalize_quote_code, DATA_DIR
from strategies import get_strategy, list_strategies
from .metrics import run_backtest


def compare_strategies(
    codes: list,
    top_n: int = 5,
    days: int = 60,
    rounds: int = 5,
    benchmark: str = None,
    scenarios: list = None,
):
    """比较所有策略的表现。

    Args:
        codes: 候选股票代码
        top_n: 每轮买入数量
        days: 回测天数
        rounds: 回测轮数
        benchmark: 基准指数代码
        scenarios: 情景列表
    """
    results = {}
    for strategy_name in list_strategies():
        print(f"  回测策略: {get_strategy(strategy_name)['label']}...", flush=True)
        report = run_backtest(strategy_name, codes, top_n, days, rounds, benchmark)
        if scenarios:
            scenario_results = {}
            for sc in scenarios:
                label = sc.get("label", "未知")
                sc_days = sc.get("days", days)
                sc_rounds = sc.get("rounds", max(1, rounds // 2))
                sr = run_backtest(
                    strategy_name, codes, top_n, sc_days, sc_rounds, benchmark
                )
                scenario_results[label] = {
                    "total_return_pct": sr.get("total_return_pct"),
                    "sharpe_ratio": sr.get("sharpe_ratio"),
                    "max_drawdown_pct": sr.get("max_drawdown_pct"),
                    "win_rate_pct": sr.get("win_rate_pct"),
                }
            report["scenarios"] = scenario_results
        results[strategy_name] = report
    return results


def optimize_weights(codes: list, strategy_name: str, top_n: int = 5, days: int = 60):
    """
    简单网格搜索优化策略权重。

    在当前权重基础上，对 quality/valuation/momentum/liquidity 各 ±5% 做网格搜索。
    权重通过 run_backtest(weights=...) 参数传入，**不修改全局 STRATEGIES**，
    避免并发场景下的数据竞争（issue: backtest 直接修改全局字典）。
    """
    base_keys = ["quality", "valuation", "momentum", "liquidity"]
    original_weights = {k: get_strategy(strategy_name)[k] for k in base_keys}

    best_score = -999
    best_weights = original_weights.copy()
    results = []

    steps = [-0.05, 0, 0.05]

    print(f"  基准权重: {original_weights}", flush=True)
    base_report = run_backtest(strategy_name, codes, top_n, days, 3)
    base_score = base_report.get("sharpe_ratio", 0)
    print(f"  基准夏普: {base_score:.2f}", flush=True)

    for key in base_keys:
        for step in steps:
            test_weights = original_weights.copy()
            test_weights[key] = max(0.05, test_weights[key] + step)

            total = sum(test_weights.values())
            test_weights = {k: v / total for k, v in test_weights.items()}

            # 通过 weights 参数传入，不修改全局 STRATEGIES（避免并发数据竞争）
            report = run_backtest(
                strategy_name, codes, top_n, days, 3, weights=test_weights
            )

            score = report.get("sharpe_ratio", 0)

            results.append(
                {
                    "weights": {k: round(v, 3) for k, v in test_weights.items()},
                    "sharpe": score,
                    "return": report.get("total_return_pct", 0),
                }
            )

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


def _fetch_benchmark_return(benchmark_code: str, days: int) -> float | None:
    """拉取基准指数在最近 N 个交易日的累计涨跌幅。

    Args:
        benchmark_code: sh000300 / sh000016 / sz399006 等
        days: 回看天数（会比实际交易日略大，确保覆盖）

    Returns:
        累计涨跌幅（%），失败返回 None
    """
    try:
        from data import get_kline

        # 多取几天，确保覆盖 N 个交易日
        bars = get_kline(benchmark_code, scale=240, datalen=days + 10)
        if not bars or len(bars) < 2:
            return None
        # 取最后 days 根
        bars = bars[-days:] if len(bars) > days else bars
        first_close = bars[0].close
        last_close = bars[-1].close
        if first_close <= 0:
            return None
        return round((last_close / first_close - 1) * 100, 2)
    except Exception as e:
        print(f"⚠️  基准收益拉取失败: {e}", file=sys.stderr)
        return None


def load_test_universe():
    """加载测试股票池（过滤掉元数据 key 和非列表值）。"""
    path = DATA_DIR / "sector_stocks.json"
    if not path.exists():
        return []
    sectors = json.loads(path.read_text(encoding="utf-8"))
    all_codes = []
    for k, items in sectors.items():
        if isinstance(items, list):
            all_codes.extend(items)
    return sorted(set(all_codes))


def main():
    from common.cache import cleanup_tmp_files

    cleanup_tmp_files()

    parser = argparse.ArgumentParser(description="多因子选股策略回测", add_help=False)
    from common.version import __version__

    parser.add_argument(
        "-v", "--version", action="version", version=f"backtest {__version__}"
    )
    parser.add_argument("-h", "--help", action="help")
    parser.add_argument(
        "--strategy", choices=list_strategies(), default="balanced", help="回测策略"
    )
    parser.add_argument("--all", action="store_true", help="比较所有策略")
    parser.add_argument("--optimize", action="store_true", help="优化权重")
    parser.add_argument("--top", type=int, default=5, help="每轮买入数量")
    parser.add_argument("--days", type=int, default=60, help="回测天数")
    parser.add_argument("--rounds", type=int, default=5, help="回测轮数")
    parser.add_argument("--codes", help="自定义股票代码（逗号分隔）")
    parser.add_argument(
        "--benchmark", default=None, help="基准指数代码（如 sh000300 沪深300）"
    )
    parser.add_argument("--scenarios", action="store_true", help="运行情景分析")
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    if args.codes:
        codes = [normalize_quote_code(c) for c in args.codes.split(",")]
    else:
        codes = load_test_universe()

    if not codes:
        print("❌ 无可用股票池", file=sys.stderr)
        sys.exit(1)

    print(f"📊 回测股票池: {len(codes)} 只", flush=True)

    if len(codes) < args.top:
        print(
            f"⚠️  股票池 ({len(codes)}) 少于 top ({args.top})，"
            f"自动调整为 top={len(codes)}",
            flush=True,
        )

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
        print(
            f"\n📈 比较所有策略 (top={args.top}, days={args.days}, rounds={args.rounds})",
            flush=True,
        )
        scenarios = None
        if args.scenarios:
            scenarios = [
                {"label": "近1月", "days": 20, "rounds": 3},
                {"label": "近3月", "days": 60, "rounds": 3},
                {"label": "近6月", "days": 120, "rounds": 3},
            ]
        results = compare_strategies(
            codes,
            args.top,
            args.days,
            args.rounds,
            benchmark=args.benchmark,
            scenarios=scenarios,
        )
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            header = f"{'策略':<18} {'总收益%':>8} {'夏普':>6} {'信息比':>7} {'最大回撤%':>8} {'胜率%':>6}"
            if scenarios:
                header += f" {'情景(收%)':>30}"
            print(header)
            print("-" * (len(header) + 10))
            for name, report in results.items():
                if "error" in report:
                    print(f"{name:<18} {'ERROR':>8}")
                else:
                    line = (
                        f"{name:<18} {report['total_return_pct']:>8.2f} "
                        f"{report['sharpe_ratio']:>6.2f} "
                        f"{report.get('information_ratio', 0):>7.2f} "
                        f"{report['max_drawdown_pct']:>8.2f} "
                        f"{report['win_rate_pct']:>6.1f}"
                    )
                    if report.get("scenarios"):
                        scenario_str = "; ".join(
                            (
                                f"{k}:{v['total_return_pct']}%"
                                if v.get("total_return_pct") is not None
                                else f"{k}:?"
                            )
                            for k, v in report["scenarios"].items()
                        )
                        line += f" {scenario_str[:30]:>30}"
                    print(line)
            # 基准对比行
            if args.benchmark:
                bench_pct = _fetch_benchmark_return(args.benchmark, args.days)
                if bench_pct is not None:
                    print("-" * (len(header) + 10))
                    print(
                        f"{'基准 ' + args.benchmark:<18} {bench_pct:>8.2f} {'-':>6} {'-':>7} {'-':>8} {'-':>6}"
                    )

    else:
        print(
            f"\n📈 回测策略: {args.strategy} (top={args.top}, days={args.days}, rounds={args.rounds})",
            flush=True,
        )
        if args.benchmark:
            print(f"   基准: {args.benchmark}")
        report = run_backtest(
            args.strategy,
            codes,
            args.top,
            args.days,
            args.rounds,
            benchmark=args.benchmark,
        )
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
            if report.get("information_ratio"):
                print(f"信息比率: {report['information_ratio']:.2f}")
            print(f"最大回撤: {report['max_drawdown_pct']:.2f}%")
            print(f"盈亏比: {report.get('profit_loss_ratio', 0):.2f}")
            print(f"年化换手: {report.get('annual_turnover', 0)} 次")
            if report.get("win_by_position"):
                wp = report["win_by_position"]
                print(
                    f"分位置胜率: 早期{wp.get('early', '-')}% / 中期{wp.get('mid', '-')}% / 后期{wp.get('late', '-')}%"
                )

            # ASCII 可视化
            try:
                from .visualize import render_return_curve, render_drawdown_chart

                # 从 round_details 提取收益序列
                round_details = report.get("round_details", [{}])
                returns = round_details[0].get("returns", []) if round_details else []
                if not returns:
                    returns = [report.get("avg_return_pct", 0)] * report.get(
                        "rounds", 1
                    )

                print()
                print(render_return_curve(returns, width=50, height=10))
                print()
                print(render_drawdown_chart(returns, width=50, height=6))
            except Exception:
                pass  # 可视化失败不影响主流程


if __name__ == "__main__":
    main()
