"""
回测 CLI 入口：策略比较、权重优化、命令行解析。
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import normalize_quote_code, DATA_DIR
from strategies import get_strategy, list_strategies, get_validation
from .metrics import run_backtest


def _attach_validation(report) -> None:
    """给回测 JSON 输出挂上策略验证状态。

    透传 validation_status（in_sample / oos_verified / unknown）和
    validation_note（提示文本），让消费方区分 in_sample 拟合数字与
    外样本验证过的实盘表现。元数据从 STRATEGY_VALIDATION 读（与
    STRATEGIES 权重 dict 分离，避免污染因子加权计算）。

    Args:
        report: run_backtest 返回的 dict，会被原地修改。
    """
    if not isinstance(report, dict):
        return
    strategy_name = report.get("strategy")
    if not strategy_name:
        return
    val = get_validation(strategy_name)
    report["_validation_status"] = val["validation_status"]
    report["_validation_note"] = val["validation_note"]


def compare_strategies(
    codes: list,
    top_n: int = 5,
    days: int = 60,
    rounds: int = 5,
    benchmark=None,
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
        _attach_validation(report)
        results[strategy_name] = report
    return results


def optimize_weights(
    codes: list,
    strategy_name: str,
    top_n: int = 5,
    days: int = 60,
    validate: bool = True,
):
    """
    简单网格搜索优化策略权重。

    在当前权重基础上，对 quality/valuation/momentum/liquidity 各 ±5% 做网格搜索。
    权重通过 run_backtest(weights=...) 参数传入，**不修改全局 STRATEGIES**，
    避免并发场景下的数据竞争（issue: backtest 直接修改全局字典）。

    validate=True 时（默认）：对 best_weights 在 60/120/240 三个窗口做
    跨窗口验证（单窗口优化会过拟合历史，优化结果必须在多个窗口同时为
    正收益才可信）。
    """
    # 全因子优化（修复：原只取 4 键，volatility/chip/dividend/event 合计
    # 34% 权重被置零，"优化"实为 4 因子策略 vs 7 因子基线的对比）
    base_keys = [
        k
        for k in get_strategy(strategy_name)
        if k not in ("label", "two_stage", "analyst")
    ]
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

    result = {
        "strategy": strategy_name,
        "best_weights": {k: round(v, 3) for k, v in best_weights.items()},
        "best_sharpe": round(best_score, 3),
        "baseline_sharpe": round(base_score, 3),
        "improvement": round(best_score - base_score, 3),
        "all_results": results,
    }

    # 跨窗口验证：best_weights 在 60/120/240 日窗口的表现
    if validate:
        validation = {}
        for vdays in (60, 120, 240):
            vreport = run_backtest(
                strategy_name, codes, top_n, vdays, 3, weights=best_weights
            )
            validation[str(vdays)] = {
                "total_return_pct": vreport.get("total_return_pct", 0),
                "sharpe_ratio": vreport.get("sharpe_ratio", 0),
                "win_rate_pct": vreport.get("win_rate_pct", 0),
            }
        robust = all(v["total_return_pct"] > 0 for v in validation.values())
        result["cross_window_validation"] = validation
        result["robust"] = robust

    _attach_validation(result)
    return result


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


def _print_report_meta(meta: dict | None):
    """统一输出报告尾部的时间戳/数据源标记（SKILL 硬约束）。"""
    if not meta:
        return
    ts = meta.get("generated_at", "-")
    sources = meta.get("data_sources") or ["K线(多源聚合)"]
    bench_src = meta.get("benchmark_source")
    is_deg = meta.get("is_degraded", False)
    parts = [f"📅 报告生成: {ts}", f"🔌 数据源: {', '.join(sources)}"]
    if bench_src:
        parts.append(f"基准: {bench_src}")
    if is_deg:
        parts.append("⚠️  存在数据降级")
    print(" | ".join(parts))


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
    parser.add_argument(
        "--validate",
        action="store_true",
        default=True,
        help="优化后对 best_weights 做 60/120/240 日跨窗口验证（默认开启）",
    )
    parser.add_argument(
        "--no-validate",
        dest="validate",
        action="store_false",
        help="关闭跨窗口验证（不推荐）",
    )
    parser.add_argument("--top", type=int, default=5, help="每轮买入数量")
    parser.add_argument("--days", type=int, default=60, help="回测天数")
    parser.add_argument("--rounds", type=int, default=5, help="回测轮数")
    parser.add_argument("--codes", help="自定义股票代码（逗号分隔）")
    parser.add_argument(
        "--benchmark",
        default=None,
        help="基准指数代码（如 sh000300 沪深300），多个用逗号分隔（如 sh000300,sh000016）",
    )
    parser.add_argument("--scenarios", action="store_true", help="运行情景分析")
    parser.add_argument(
        "--walk-forward",
        action="store_true",
        help="Walk-forward 回测（train+test 滚动窗口 OOS 验证）",
    )
    parser.add_argument(
        "--train-days",
        type=int,
        default=120,
        help="Walk-forward 训练段天数（默认 120）",
    )
    parser.add_argument(
        "--test-days",
        type=int,
        default=30,
        help="Walk-forward 测试段天数（默认 30，OOS 窗口）",
    )
    parser.add_argument(
        "--n-windows",
        type=int,
        default=5,
        help="Walk-forward 窗口数量（默认 5）",
    )
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    if args.codes:
        codes = [normalize_quote_code(c) for c in args.codes.split(",")]
    else:
        codes = load_test_universe()

    # 多基准解析：--benchmark sh000300,sh000016,sz399006
    benchmarks: list[str] = []
    if args.benchmark:
        benchmarks = [
            normalize_quote_code(b) for b in args.benchmark.split(",") if b.strip()
        ]
    benchmark_arg = benchmarks[0] if len(benchmarks) == 1 else (benchmarks or None)

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

    if args.walk_forward:
        from .walk_forward import run_walk_forward, WalkForwardConfig

        print(
            f"\n🔄 Walk-forward 回测: {args.strategy} "
            f"(train={args.train_days}d, test={args.test_days}d, "
            f"windows={args.n_windows}, top={args.top})",
            flush=True,
        )
        config = WalkForwardConfig(
            strategy_name=args.strategy,
            codes=codes,
            train_days=args.train_days,
            test_days=args.test_days,
            n_windows=args.n_windows,
            top_n=args.top,
        )
        wf_result = run_walk_forward(config)
        d = wf_result.to_dict()
        if args.json:
            print(json.dumps(d, ensure_ascii=False, indent=2))
        else:
            print(f"\n{'指标':<20} {'OOS':>10} {'IS(参考)':>10}")
            print("-" * 42)
            print(
                f"{'总收益%':<20} {d['oos_total_return_pct']:>10.2f} {d['is_total_return_pct']:>10.2f}"
            )
            print(f"{'夏普比率':<20} {d['oos_sharpe']:>10.2f} {d['is_sharpe']:>10.2f}")
            print(f"{'胜率%':<20} {d['oos_win_rate_pct']:>10.1f} {'-':>10}")
            print(f"{'最大回撤%':<20} {d['oos_max_drawdown_pct']:>10.2f} {'-':>10}")
            print(f"\n有效窗口: {d['n_valid_windows']}/{args.n_windows}")
            if d.get("errors"):
                print(f"错误窗口: {len(d['errors'])}")
            print("\n💡 OOS = Out-of-Sample（策略未见过的数据），比全样本回测更可信")
            _print_report_meta(
                {
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "data_sources": ["K线(多源聚合)"],
                    "is_degraded": any(
                        w.get("status") != "ok" for w in wf_result.windows
                    ),
                }
            )

    elif args.optimize:
        print(f"\n🔧 优化策略权重: {args.strategy}", flush=True)
        result = optimize_weights(
            codes, args.strategy, args.top, args.days, validate=args.validate
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"\n最优权重: {result['best_weights']}")
            print(f"最优夏普: {result['best_sharpe']:.3f}")
            print(f"基准夏普: {result['baseline_sharpe']:.3f}")
            print(f"提升: {result['improvement']:+.3f}")
            if "cross_window_validation" in result:
                print("\n📐 跨窗口验证（60/120/240 日）:")
                for vdays, v in result["cross_window_validation"].items():
                    print(
                        f"  {vdays}日: 收益 {v['total_return_pct']:+.2f}% "
                        f"夏普 {v['sharpe_ratio']:.2f} 胜率 {v['win_rate_pct']:.1f}%"
                    )
                if result.get("robust"):
                    print("✅ 优化权重通过跨窗口验证（三窗口均为正收益）")
                else:
                    print(
                        "⚠️  优化权重未通过跨窗口验证（存在负收益窗口），"
                        "不建议实盘使用——单窗口优化可能过拟合历史"
                    )
            _print_report_meta(
                {
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "data_sources": ["K线(多源聚合)"],
                }
            )

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
            benchmark=benchmark_arg,
            scenarios=scenarios,
        )
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            header = f"{'策略':<18} {'总收益%':>8} {'夏普':>6} {'索提诺':>7} {'信息比':>7} {'最大回撤%':>8} {'胜率%':>6}"
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
                        f"{report.get('sortino_ratio', 0):>7.2f} "
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
            # 基准对比行（多基准每个一行）
            if benchmarks:
                print("-" * (len(header) + 10))
                for bm in benchmarks:
                    bench_pct = _fetch_benchmark_return(bm, args.days)
                    if bench_pct is not None:
                        print(
                            f"{'基准 ' + bm:<18} {bench_pct:>8.2f} {'-':>6} {'-':>7} {'-':>7} {'-':>8} {'-':>6}"
                        )
            # 报告尾行：时间戳 + 数据源
            any_meta = next(
                (r.get("meta") for r in results.values() if r.get("meta")), None
            )
            _print_report_meta(any_meta)

    else:
        print(
            f"\n📈 回测策略: {args.strategy} (top={args.top}, days={args.days}, rounds={args.rounds})",
            flush=True,
        )
        if benchmarks:
            print(f"   基准: {', '.join(benchmarks)}")
        report = run_backtest(
            args.strategy,
            codes,
            args.top,
            args.days,
            args.rounds,
            benchmark=benchmark_arg,
        )
        _attach_validation(report)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif "error" in report:
            # M5: 错误模式仍输出 footer（SKILL.md 硬约束），
            # 让 SKILL 渲染层和 LLM caller 能看到降级标志。
            print(f"❌ {report['error']}")
            _print_report_meta(
                {
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "data_sources": ["K线(多源聚合)"],
                    "is_degraded": True,
                }
            )
        else:
            print(f"\n总收益: {report['total_return_pct']:.2f}%")
            print(f"平均收益: {report['avg_return_pct']:.2f}%")
            print(f"最大收益: {report['max_return_pct']:.2f}%")
            print(f"最小收益: {report['min_return_pct']:.2f}%")
            print(f"胜率: {report['win_rate_pct']:.1f}%")
            print(f"夏普比率: {report['sharpe_ratio']:.2f}")
            print(f"索提诺比率: {report.get('sortino_ratio', 0):.2f}")
            info_ratios = report.get("information_ratios") or {}
            if info_ratios:
                for bm, ratio in info_ratios.items():
                    print(f"信息比率({bm}): {ratio:.2f}")
            elif report.get("information_ratio"):
                print(f"信息比率: {report['information_ratio']:.2f}")
            print(f"最大回撤: {report['max_drawdown_pct']:.2f}%")
            print(f"卡玛比率: {report.get('calmar_ratio', 0):.2f}")
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

            _print_report_meta(report.get("meta"))


if __name__ == "__main__":
    main()
