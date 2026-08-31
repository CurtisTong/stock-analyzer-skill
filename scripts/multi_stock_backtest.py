#!/usr/bin/env python3
"""外样本多股票回测 + 基准对比（PR-G：解决 71.4% CLAIM 单股过拟合问题）。

为什么需要这个脚本：
  ma_volume_combined 策略的 71.4% / 6.39% 是 5 只股票样本内拟合结果
  （self-acknowledged in config.json multi_stock_validation.avg_win_rate=59.7）。
  本脚本把样本扩展到 50+ 只 A 股、并叠加沪深 300 / 中证 500 基准对比，
  输出"样本外"胜率和超额收益（alpha），让 CLAIM 有统计意义。

用法：
  python3 scripts/multi_stock_backtest.py                    # 默认 50 只 + 2 基准
  python3 scripts/multi_stock_backtest.py --top 30           # 自定义 top_n
  python3 scripts/multi_stock_backtest.py --codes sh600519,sz000807  # 指定股票
  python3 scripts/multi_stock_backtest.py --output docs/backtest-multi-stock.md

依赖：scripts/backtest/engine.py:simulate_strategy + data_fetcher_manager
（首次跑会从腾讯/东财拉 K 线，需要联网；缓存后离线可用）
"""

import argparse
from common.cli_base import create_parser, handle_errors
from datetime import datetime
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent

# 50+ 只 A 股跨板块抽样（覆盖消费/医药/科技/金融/周期/能源/制造/材料 8 大类）
# 故意不用 5 只样本内拟合过的股票（宝丰能源/恒瑞医药等）
DEFAULT_CODES = [
    # 消费（白酒/家电/食品）
    "sh600519",
    "sz000858",
    "sz000333",
    "sz000651",
    "sh600887",
    "sh600690",
    "sz000418",
    "sh603288",
    # 医药
    "sh600276",
    "sz300760",
    "sh603259",
    "sh600196",
    "sz000538",
    "sz300015",
    "sh600085",
    # 科技（半导体/软件/通信）
    "sz002371",
    "sz300750",
    "sz002594",
    "sh688981",
    "sh600588",
    "sz000063",
    "sh600271",
    # 金融（银行/保险/证券）
    "sh601398",
    "sh601288",
    "sh600036",
    "sh601318",
    "sh600030",
    "sh601166",
    "sh601628",
    # 周期（钢铁/有色/化工/煤炭）
    "sh600019",
    "sh601899",
    "sh600585",
    "sh601088",
    "sh600010",
    "sh601225",
    "sh600111",
    # 能源（石油/电力/天然气）
    "sh601857",
    "sh600028",
    "sh600886",
    "sh600025",
    "sh600900",
    "sh600188",
    # 制造（汽车/工程机械/船舶）
    "sz000625",
    "sh600031",
    "sh601766",
    "sh601012",
    "sh600438",
    "sh600761",
    "sh600320",
    # 材料（建材/化工/造纸）
    "sh600176",
    "sh600309",
    "sh601992",
    "sh600219",
    "sh600801",
    "sh600585",
    "sh600352",
]

# 基准指数（沪深 300 / 中证 500）
BENCHMARKS = [
    ("sh000300", "沪深300"),
    ("sh000905", "中证500"),
]


def load_codes(arg_codes: str | None) -> list[str]:
    """加载股票代码：CLI 参数 → 默认 50+ 只。

    空字符串或仅 ',' 时也走默认（防止 CLI 传空参数意外跑空股票池）。
    """
    if arg_codes:
        parsed = [c.strip() for c in arg_codes.split(",") if c.strip()]
        if parsed:
            return parsed
    # 去重（DEFAULT_CODES 跨类别有重复）
    seen = set()
    deduped = []
    for c in DEFAULT_CODES:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped


def run_one_strategy(
    strategy_name: str,
    codes: list[str],
    *,
    top_n: int = 5,
    holding_days: int = 5,
    total_days: int = 60,
) -> dict:
    """跑单个策略在指定股票池上的回测，返回结构化结果。"""
    try:
        from backtest.metrics import run_backtest
    except ImportError as e:
        return {"error": f"metrics import failed: {e}", "strategy": strategy_name}

    try:
        # 修复：改调 run_backtest（返回 total_return_pct/sharpe_ratio 等完整指标），
        # 而非 simulate_strategy（只返回原始收益序列，导致 format_report 读取不到字段而全零）。
        # v1.22.1 修复：透传 holding_days（此前被静默忽略，CLI 打印"持有 X 日"与实际不符）。
        result = run_backtest(
            strategy_name=strategy_name,
            codes=codes,
            top_n=top_n,
            days=total_days,
            holding_days=holding_days,
        )
        return {
            "strategy": strategy_name,
            "codes_count": len(codes),
            "result": result,
        }
    except Exception as e:
        return {
            "strategy": strategy_name,
            "codes_count": len(codes),
            "error": f"{type(e).__name__}: {e}",
        }


def run_benchmark(code: str, name: str, total_days: int = 60, holding_days: int | None = None) -> dict:
    """跑基准指数回测（用 balanced 策略权重在指数上）。"""
    try:
        from backtest.metrics import run_backtest
    except ImportError as e:
        return {"error": f"metrics import failed: {e}", "benchmark": name}

    try:
        result = run_backtest(
            strategy_name="balanced",
            codes=[code],
            top_n=1,
            days=total_days,
            holding_days=holding_days,
        )
        return {"benchmark": name, "code": code, "result": result}
    except Exception as e:
        return {"benchmark": name, "code": code, "error": f"{type(e).__name__}: {e}"}


def format_report(
    strategy_results: list[dict],
    benchmark_results: list[dict],
    codes: list[str],
) -> str:
    """生成 markdown 报告。"""
    lines = []
    lines.append("# 多股票外样本回测报告\n")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"股票池: {len(codes)} 只 A 股\n")
    lines.append("")

    lines.append("## 1. 策略回测结果\n")
    lines.append("| 策略 | 股票数 | 总收益% | 平均收益% | 夏普 | 最大回撤% | 胜率% |")
    lines.append("|------|--------|---------|-----------|------|-----------|-------|")
    for sr in strategy_results:
        if "error" in sr:
            lines.append(
                f"| {sr.get('strategy', '?')} | {sr.get('codes_count', 0)} | ⚠️ {sr['error'][:40]} | - | - | - | - |"
            )
            continue
        r = sr["result"]
        # run_backtest 返回 *_pct 为数值（如 15.0 表示 15%），直接显示，不用 % 格式化
        lines.append(
            f"| {sr['strategy']} | {sr['codes_count']} | "
            f"{r.get('total_return_pct', 0):.2f} | {r.get('avg_return_pct', 0):.2f} | "
            f"{r.get('sharpe_ratio', 0):.2f} | {r.get('max_drawdown_pct', 0):.2f} | "
            f"{r.get('win_rate_pct', 0):.1f} |"
        )
    lines.append("")

    lines.append("## 2. 基准对比\n")
    lines.append("| 基准 | 代码 | 总收益% | 平均收益% | 夏普 | 最大回撤% |")
    lines.append("|------|------|---------|-----------|------|-----------|")
    for br in benchmark_results:
        if "error" in br:
            lines.append(f"| {br.get('benchmark', '?')} | {br.get('code', '?')} | ⚠️ {br['error'][:40]} | - | - | - |")
            continue
        r = br["result"]
        lines.append(
            f"| {br['benchmark']} | {br['code']} | "
            f"{r.get('total_return_pct', 0):.2f} | {r.get('avg_return_pct', 0):.2f} | "
            f"{r.get('sharpe_ratio', 0):.2f} | {r.get('max_drawdown_pct', 0):.2f} |"
        )
    lines.append("")

    lines.append("## 3. 超额收益（Alpha）\n")
    if strategy_results and benchmark_results:
        sr = strategy_results[0]
        br = benchmark_results[0]
        if "error" not in sr and "error" not in br:
            # 用平均收益差近似 alpha（run_backtest 未返回年化收益）
            alpha = sr["result"].get("avg_return_pct", 0) - br["result"].get("avg_return_pct", 0)
            lines.append(f"- {sr['strategy']} 相对 {br['benchmark']}: alpha = {alpha:+.2f}%\n")

    lines.append("## 4. 重要提示\n")
    lines.append("- ⚠️ 本回测为**样本外**测试，股票池与 ma_volume_combined 原 5 只样本不重叠")
    lines.append("- ⚠️ 基准对比使用同期沪深 300 / 中证 500 走势")
    lines.append("- ⚠️ 历史业绩不代表未来收益")
    lines.append("- ⚠️ 数据来自腾讯/东财，存在数据缺失/接口调整风险")
    lines.append("")
    lines.append("生成命令：")
    lines.append("```bash")
    lines.append("python3 scripts/multi_stock_backtest.py")
    lines.append("```\n")

    return "\n".join(lines)


def main() -> None:
    parser = create_parser(description="外样本多股票回测 + 基准对比")
    parser.add_argument("--codes", help="逗号分隔股票代码列表（默认 50 只跨板块）")
    parser.add_argument("--top", type=int, default=5, help="每个时间点持有股票数")
    parser.add_argument("--holding-days", type=int, default=5)
    parser.add_argument("--total-days", type=int, default=60)
    parser.add_argument("--strategies", default="balanced,ma_volume_momentum", help="逗号分隔策略列表")
    parser.add_argument("--output", help="报告输出路径（默认打印到 stdout）")
    parser.add_argument(
        "--update-validation",
        action="store_true",
        help="跑完后自动把结果写进 data/strategy_oos_validation.json，" "覆盖 STRATEGY_VALIDATION 默认 in_sample 状态",
    )
    parser.add_argument(
        "--pool-type",
        default="default",
        choices=["default", "large"],
        help="本次回测的池类型标识（default=全量 sector 池 / large=跨板块大票池），"
        "写入 validation JSON 供双池联合判定",
    )
    parser.add_argument(
        "--require-all-pools",
        action="store_true",
        help="双池联合判定：读取 JSON 中已有的全部池结果，所有池都达标才升级 "
        "oos_verified（单池 OOS 受池构成影响极大，须双池一致）",
    )
    args = parser.parse_args()

    codes = load_codes(args.codes)
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]

    print(f"📊 股票池: {len(codes)} 只")
    print(f"🎯 策略: {', '.join(strategies)}")
    print(f"⏱️  回测窗口: {args.total_days} 日 / 持有 {args.holding_days} 日 / top {args.top}")
    print()

    strategy_results = []
    for sname in strategies:
        print(f"⏳ 跑策略 {sname} ...")
        result = run_one_strategy(
            sname,
            codes,
            top_n=args.top,
            holding_days=args.holding_days,
            total_days=args.total_days,
        )
        strategy_results.append(result)
        if "error" in result:
            print(f"   ❌ {result['error']}")
        else:
            r = result["result"]
            print(f"   ✅ 总收益 {r.get('total_return_pct', 0):.2f}%, 胜率 {r.get('win_rate_pct', 0):.1f}%")

    benchmark_results = []
    for code, name in BENCHMARKS:
        print(f"⏳ 跑基准 {name}({code}) ...")
        result = run_benchmark(code, name, total_days=args.total_days, holding_days=args.holding_days)
        benchmark_results.append(result)
        if "error" in result:
            print(f"   ❌ {result['error']}")
        else:
            r = result["result"]
            print(f"   ✅ 总收益 {r.get('total_return_pct', 0):.2f}%")

    report = format_report(strategy_results, benchmark_results, codes)

    if args.output:
        out_path = PKG_ROOT / args.output
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"\n📝 报告已写入: {args.output}")
    else:
        print("\n" + report)

    if args.update_validation:
        _update_validation(
            strategy_results,
            n_codes=len(codes),
            pool_type=args.pool_type,
            require_all_pools=args.require_all_pools,
        )


def _update_validation(
    strategy_results: list[dict],
    *,
    n_codes: int,
    pool_type: str = "default",
    require_all_pools: bool = False,
) -> None:
    """把本次回测结果写进 data/strategy_oos_validation.json。

    调用 scripts/strategies/oos_validation 的状态机：
    - 股票池 ≥ 30 + 胜率 ≥ 50% + 累计收益 > 0 → oos_verified
    - 否则 → in_sample（保留，但加备注说明原因）

    require_all_pools=True 时改用 evaluate_multi_pool 联合判定：读取 JSON 中
    已存在的全部池结果（含本次写入的），所有池均达标才升级 oos_verified。

    覆盖 registry 默认 STRATEGY_VALIDATION；删除 JSON 文件可恢复默认。
    """
    from strategies.oos_validation import (
        build_oos_note,
        evaluate_multi_pool,
        evaluate_oos,
        load_oos_overrides,
        save_oos_result,
    )

    print("\n📝 更新 data/strategy_oos_validation.json ...")
    for r in strategy_results:
        sname = r.get("strategy")
        if not sname or "error" in r:
            continue
        result = r["result"]
        win_rate = float(result.get("win_rate_pct", 0) or 0)
        total_ret = float(result.get("total_return_pct", 0) or 0)
        sharpe = float(result.get("sharpe_ratio", 0) or 0)
        max_dd = float(result.get("max_drawdown_pct", 0) or 0)

        # 先按单池状态机判定并写入本池结果
        status = evaluate_oos(win_rate, n_codes, total_ret)
        note = build_oos_note(win_rate, n_codes, total_ret)
        if status == "in_sample":
            note += "（未达阈值，保持 in_sample）"

        save_oos_result(
            sname,
            validation_status=status,
            validation_note=note,
            win_rate_pct=win_rate,
            n_stocks=n_codes,
            total_return_pct=total_ret,
            pool_type=pool_type,
            extra={"sharpe_ratio": sharpe, "max_drawdown_pct": max_dd},
        )

        # 双池联合判定：汇总 JSON 中该策略全部池的结果
        if require_all_pools:
            overrides = load_oos_overrides().get(sname, {})
            pools = overrides.get("pools", {}) if isinstance(overrides, dict) else {}
            if not pools:
                pools = {pool_type: (win_rate, n_codes, total_ret)}
            # pools 值为 dict（含 win_rate_pct/n_stocks/total_return_pct），
            # 转成 evaluate_multi_pool 期望的元组
            pool_results = {
                pt: (
                    float(p.get("win_rate_pct", 0) or 0),
                    int(p.get("n_stocks", 0) or 0),
                    float(p.get("total_return_pct", 0) or 0),
                )
                for pt, p in pools.items()
                if isinstance(p, dict)
            }
            status, note = evaluate_multi_pool(pool_results)
            save_oos_result(
                strategy_name=sname,
                validation_status=status,
                validation_note=note,
                win_rate_pct=win_rate,
                n_stocks=n_codes,
                total_return_pct=total_ret,
                pool_type=pool_type,
                extra={"sharpe_ratio": sharpe, "max_drawdown_pct": max_dd},
            )
        marker = "✅" if status == "oos_verified" else "⚠️ "
        print(f"   {marker} {sname}: {status} ({win_rate:.1f}% / {n_codes} 只)")


if __name__ == "__main__":
    main()
