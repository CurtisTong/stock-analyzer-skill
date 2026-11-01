#!/usr/bin/env python3
"""因子 IC 评估 CLI（v1.26 阶段 2）。

因子 IC（Information Coefficient）= 因子分与后续收益的秩相关（Spearman）。
IC > 0 表示因子有效（高因子分 → 高收益），IC ≈ 0 表示无预测力。

背景：仓库里 `strategies/factor/ic.py` 提供了 IC 计算与持久化，但整条链路
是纸面的——引擎算了 parts 不输出、`compute_all_factor_ic`/`save_ic`/`load_ic`
都没有调用方。本 CLI 把链路接通并让它可用：

    python3 scripts/factor_ic.py --strategy growth_momentum --days 120
    python3 scripts/factor_ic.py --strategy balanced --days 90 --save

用法说明：
- IC 评估需要**足够样本**（每个因子至少 5 个非缺失观测）；
- 情绪因子（sentiment）依赖历史快照，用户需先按日采集
  （`python3 scripts/sentiment_panel.py refresh`），否则该因子样本为 0。
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.cli_base import create_parser, handle_errors  # noqa: E402


def _load_universe(count: int = 20):
    """默认股票池（与回测 CLI 保持一致）。"""
    from backtest.cli import load_test_universe

    return load_test_universe()[:count]


def cmd_evaluate(args):
    """跑回测并计算因子 IC。"""
    from backtest.metrics import run_backtest
    from strategies.factor.ic import compute_all_factor_ic, compute_ic_by_regime, save_ic

    codes = [c.strip() for c in args.codes.split(",")] if args.codes else _load_universe(args.universe)
    if not codes:
        print("❌ 无可用股票池", file=sys.stderr)
        return 1

    print(f"回测 {args.strategy}（{len(codes)} 只，{args.days} 日）...", flush=True)
    report = run_backtest(
        args.strategy,
        codes,
        top_n=args.top,
        days=args.days,
        rounds=args.rounds,
        benchmark=args.benchmark or None,
    )
    if "error" in report:
        print(f"❌ 回测失败: {report['error']}", file=sys.stderr)
        return 1

    selections = report.get("selections") or []
    if not selections:
        print("❌ 回测无选股明细", file=sys.stderr)
        return 1

    ic_all = compute_all_factor_ic(selections)
    ic_by_regime = compute_ic_by_regime(selections)
    from strategies.factor.ic import compute_factor_ic_stats

    ic_stats = {f: compute_factor_ic_stats(selections, f) for f in ic_all}

    if args.json_output:
        print(
            json.dumps(
                {
                    "strategy": args.strategy,
                    "samples": len(selections),
                    "ic": ic_all,
                    "ic_stats": ic_stats,
                    "min_samples": args.min_samples,
                    "warnings": [
                        # v1.28.0：零样本单独告警——IC 未计算 ≠ 因子无效
                        (
                            f"{f}: 无有效样本（IC 未计算，不能据此判定因子有效性）"
                            if ic_stats.get(f, {}).get("samples", 0) == 0
                            else f"{f}: 样本 {ic_stats[f]['samples']} < 门槛 {args.min_samples}，IC 无统计意义"
                        )
                        for f in ic_all
                        if ic_stats.get(f, {}).get("samples", 0) == 0 or ic_stats[f]["samples"] < args.min_samples
                    ],
                    "ic_by_regime": ic_by_regime,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print()
    print(f"样本数: {len(selections)}（--min-samples 门槛: {args.min_samples}）")
    print()
    print(f"{'因子':<14} {'IC':>8} {'ICIR':>7} {'天':>4} {'样本':>6}  判读")
    print("-" * 60)
    for factor, ic in sorted(ic_all.items(), key=lambda kv: -abs(kv[1])):
        stats = ic_stats.get(factor, {})
        n_samples = stats.get("samples", 0)
        n_days = stats.get("days", 0)
        if n_samples == 0:
            # v1.28.0 修复：零样本必须显式告警。
            # ic.py 要求单日截面 ≥5 只才纳入 IC 计算，而情绪因子只在涨停/炸板池内
            # 才有值（覆盖率约 1.3%）→ 回测池与情绪池交集常为 0~4 只 →
            # samples=0、IC=0。此前因 --min-samples 默认 0（samples<0 为 False），
            # 零样本因子**不产生任何告警**，输出"无明显预测力"——与"真实测得
            # IC=0"完全无法区分，把"链路空转"伪装成"因子无效"。
            verdict = "⚠️无有效样本（IC 未计算，非因子无效）"
        elif ic > 0.05:
            verdict = "有效（正向）"
        elif ic < -0.05:
            verdict = "反向（高因子分 → 低收益）"
        else:
            verdict = "无明显预测力"
        if n_samples and n_samples < args.min_samples:
            verdict += f" ⚠️样本少于门槛({args.min_samples})，IC 无统计意义"
        elif n_samples and n_days < 5:
            verdict += " ⚠️截面天数少，参考性弱"
        print(f"{factor:<14} {ic:>8.3f} {stats.get('icir', 0):>7.2f} " f"{n_days:>4} {n_samples:>6}  {verdict}")

    if args.save:
        save_ic(ic_by_regime)
        from strategies.factor.ic import IC_FILE

        print(f"\n✅ IC 已保存到 {IC_FILE}")
    return 0


def main():
    parser = create_parser(description="因子 IC 评估（Spearman 秩相关）")
    parser.add_argument("--strategy", default="balanced", help="策略名（默认 balanced）")
    parser.add_argument("--days", type=int, default=120, help="回测天数（默认 120）")
    parser.add_argument("--rounds", type=int, default=5, help="回测轮数（默认 5）")
    parser.add_argument("--top", type=int, default=5, help="每轮买入数量（默认 5）")
    parser.add_argument("--universe", type=int, default=20, help="默认股票池只数（默认 20）")
    parser.add_argument("--codes", default="", help="自定义股票代码（逗号分隔）")
    parser.add_argument("--benchmark", default="", help="基准指数（如 sh000300）")
    parser.add_argument(
        "--min-samples",
        type=int,
        default=0,
        help="因子的最小样本数门槛：低于该值的因子判读为'无统计意义'（默认 0 = 不限制）",
    )
    parser.add_argument("--save", action="store_true", help="保存 IC 到 data/factor_ic.json")
    # -j/--json 由 create_parser 统一提供
    args = parser.parse_args()
    return cmd_evaluate(args)


if __name__ == "__main__":
    with handle_errors():
        sys.exit(main() or 0)
