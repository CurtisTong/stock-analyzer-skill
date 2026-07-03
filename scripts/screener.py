#!/usr/bin/env python3
"""
A 股多因子选股器。
用法:
  screener.py                         # 内置核心标的池，均衡策略
  screener.py --sector 资源 --top 5
  screener.py --strategy growth_momentum --json
  screener.py --codes sh600989,sz000807,300476
  screener.py --full-market --top 10                  # 全市场模式
  screener.py --full-market --sector 创业板 --top 5   # 全市场创业板
"""

import argparse
import json
import sys

from common import normalize_quote_code
from data.helpers import fetch_finance_first
from strategies import (
    STRATEGIES,  # noqa: F401 — re-export（向后兼容：测试通过 screener.STRATEGIES 访问）
    get_strategy,
    list_strategies,
    quality_score,  # noqa: F401 — re-export
    valuation_score,  # noqa: F401 — re-export
    momentum_score,  # noqa: F401 — re-export
    liquidity_score,  # noqa: F401 — re-export
    volatility_from_closes,  # noqa: F401 — re-export
    dividend_score,  # noqa: F401 — re-export
)
from strategies.thresholds import get_industry_threshold, load_industry_thresholds
from business.screening_service import (
    # 模块级函数（re-export 保持向后兼容）
    compute_features,
    compute_factor_parts,
    compute_weighted_score,
    normalize_factors_batch,
    build_result_row,
    analyze_code,
    analyze_code_phase1,
    load_universe,
    load_full_market_universe,
    pre_screen_quotes,
    apply_portfolio_constraints,
    run_screening,
    ScreeningService,
)
from data.helpers import prefetch_finance_all, prefetch_kline_all

# 向后兼容别名（原 screener 模块级函数名）
_prefetch_kline_all = prefetch_kline_all


def hard_filter(quote, fin, args):
    """硬过滤（薄包装，委托给 ScreeningService._hard_filter）。"""
    filters = {
        "min_amount": args.min_amount,
        "min_cap": args.min_cap,
        "exclude_loss": args.exclude_loss,
    }
    return ScreeningService()._hard_filter(quote, fin, filters)


def latest_finance(code):
    """获取最新财务数据（薄包装，委托给 data.helpers）。"""
    from common import normalize_finance_code

    return fetch_finance_first(normalize_finance_code(code))


def daily_features(code):
    """计算技术指标特征（薄包装，委托给 screening_service.compute_features）。"""
    return compute_features(code)


def volume_price_features(closes, volumes):
    """量价关系分析。"""
    from technical.volume import volume_analysis

    if len(closes) < 6 or len(volumes) < 6:
        return {"signal": 0, "desc": "数据不足"}
    result = volume_analysis(closes, volumes)
    if result is None:
        return {"signal": 0, "desc": "数据不足"}
    return {
        "signal": result.get("volume_price_signal", 0),
        "desc": result.get("volume_price", "量价中性"),
    }


def render(rows, strategy, top, title=None, show_chip=True):
    accepted = [r for r in rows if not r["rejected"]]
    rejected = [r for r in rows if r["rejected"]]
    accepted.sort(key=lambda r: r["score"], reverse=True)

    label = title or get_strategy(strategy)["label"]
    print(f"策略: {label} ({strategy})")
    print(f"入选: {len(accepted)} | 剔除: {len(rejected)}")
    print()

    # ROE 格式化辅助：避免 str(x)[:6] 截断效果不可预测（v1.14.2 修复）
    def _fmt_roe(v):
        try:
            return f"{float(v):.1f}"
        except (TypeError, ValueError):
            return "N/A"

    # 表头：根据 show_chip 决定是否显示筹码列
    if show_chip:
        header = "排名 | 代码 | 名称 | 行业 | 板块 | 总分 | 质量 | 估值 | 动量 | 流动 | 筹码 | PE | ROE | RSI | 20日% | 趋势 | 量价"
    else:
        header = "排名 | 代码 | 名称 | 行业 | 板块 | 总分 | 质量 | 估值 | 动量 | 流动性 | PE | ROE | RSI | 20日% | 趋势 | 量价"
    print(header)
    print("-" * len(header))
    for idx, r in enumerate(accepted[:top], 1):
        macd_icon = (
            "↑"
            if r.get("macd_signal", 0) > 0
            else "↓" if r.get("macd_signal", 0) < 0 else "→"
        )
        if show_chip:
            from business.risk_warning import chip_emoji

            chip_val = r.get("chip", 50)
            chip_display = f"{chip_emoji(chip_val)}{chip_val:>3}"
            print(
                f"{idx:>2} | {r['code']:<8} | {r['name']:<8} | {r.get('industry', '默认'):<4} | {r['board']:<4} | "
                f"{r['score']:>5} | {r['quality']:>5} | {r['valuation']:>5} | "
                f"{r['momentum']:>5} | {r['liquidity']:>5} | {chip_display:>5} | {r['pe']:>6} | "
                f"{_fmt_roe(r['roe']):>5} | {r.get('rsi', 50):>4} | {r['ret20']:>5} | {r['trend']}{macd_icon} | {r.get('vol_price', '?')}"
            )
        else:
            print(
                f"{idx:>2} | {r['code']:<8} | {r['name']:<8} | {r.get('industry', '默认'):<4} | {r['board']:<4} | "
                f"{r['score']:>5} | {r['quality']:>5} | {r['valuation']:>5} | "
                f"{r['momentum']:>5} | {r['liquidity']:>6} | {r['pe']:>6} | "
                f"{_fmt_roe(r['roe']):>5} | {r.get('rsi', 50):>4} | {r['ret20']:>5} | {r['trend']}{macd_icon} | {r.get('vol_price', '?')}"
            )

    if rejected:
        print()
        print("剔除样本:")
        for r in rejected[:10]:
            print(f"- {r['code']} {r['name']}: {', '.join(r['rejected'])}")


def render_brief(rows, strategy, top, title=None):
    """brief 模式：一句话结论 + 精简表格 + 操作建议（<500字）。"""
    accepted = [r for r in rows if not r["rejected"]]
    rejected = [r for r in rows if r["rejected"]]
    accepted.sort(key=lambda r: r["score"], reverse=True)

    label = title or get_strategy(strategy)["label"]
    top_rows = accepted[:top]

    # 一句话结论
    if not top_rows:
        print(f"策略 {label}: 无符合条件标的（剔除 {len(rejected)} 只）")
        print()
        print("可能原因:")
        print("  1. 股票池未初始化 → 运行 /screener init 或 /screener init default")
        print("  2. 筛选条件过严 → 尝试其他策略（如 balanced）")
        print("  3. 市场休市无数据 → 交易时段重试")
        return
    best = top_rows[0]
    print(
        f"策略 {label} | 入选 {len(accepted)} 剔除 {len(rejected)} | "
        f"首选 {best['code']} {best['name']} (评分 {best['score']})"
    )

    # 精简表格（仅核心列）
    header = "排名 | 代码 | 名称 | 总分 | 质量 | 估值 | 动量 | 趋势"
    print(header)
    print("-" * len(header))
    for idx, r in enumerate(top_rows, 1):
        macd_icon = (
            "↑"
            if r.get("macd_signal", 0) > 0
            else "↓" if r.get("macd_signal", 0) < 0 else "→"
        )
        print(
            f"{idx:>2} | {r['code']:<8} | {r['name']:<8} | "
            f"{r['score']:>5} | {r['quality']:>5} | {r['valuation']:>5} | "
            f"{r['momentum']:>5} | {r['trend']}{macd_icon}"
        )

    # 操作建议（基于分数分布的相对分层）
    scores = [r["score"] for r in top_rows]
    scores_sorted = sorted(scores)
    n = len(scores_sorted)
    p75 = scores_sorted[int(n * 0.75)] if n >= 4 else scores_sorted[-1]
    p50 = scores_sorted[int(n * 0.5)] if n >= 2 else scores_sorted[0]
    strong = [r for r in top_rows if r["score"] >= max(p75, 50)]
    watch = [r for r in top_rows if max(p50, 50) <= r["score"] < max(p75, 50)]
    if strong:
        names = ", ".join(f"{r['name']}" for r in strong[:3])
        print(f"→ 建议关注: {names}")
    if watch:
        names = ", ".join(f"{r['name']}" for r in watch[:3])
        print(f"→ 可观望: {names}")


def _build_parser():
    """构造 screener CLI 参数解析器（V2.1 提取便于单测复用）。"""
    parser = argparse.ArgumentParser(description="A 股多因子选股器", add_help=False)
    from common.version import __version__

    parser.add_argument(
        "-v", "--version", action="version", version=f"screener {__version__}"
    )
    parser.add_argument("-h", "--help", action="help", help="显示帮助")
    parser.add_argument("--strategy", choices=list_strategies(), default="balanced")
    parser.add_argument("--sector", help="内置板块名称，支持模糊匹配")
    parser.add_argument("--codes", help="逗号分隔代码列表，优先于 --sector")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument(
        "--min-amount", type=float, default=5000, help="最低成交额，单位万元"
    )
    parser.add_argument(
        "--min-cap", type=float, default=40, help="最低总市值，单位亿元"
    )
    parser.add_argument("--exclude-loss", action="store_true", help="剔除 EPS<=0 标的")
    parser.add_argument("--no-constraints", action="store_true", help="禁用组合约束")
    parser.add_argument("--sector-cap", type=float, default=0.30, help="单板块最高占比")
    parser.add_argument(
        "--full-market",
        action="store_true",
        help="全市场模式，从 data/all_stocks.json 加载",
    )
    parser.add_argument(
        "--board-limit",
        type=int,
        default=0,
        help="全市场模式下每板块最多保留 N 只（0=不限制）",
    )
    parser.add_argument(
        "--exclude-board",
        default="北交所",
        help="排除指定板块（如 北交所,科创板），逗号分隔，默认排除北交所",
    )
    parser.add_argument(
        "--no-normalize",
        action="store_true",
        help="禁用因子 z-score 标准化（保留 V1 原始评分）",
    )
    parser.add_argument(
        "--no-regime",
        action="store_true",
        help="禁用市场状态 overlay（保留 V1 固定权重）",
    )
    parser.add_argument(
        "--no-chip",
        action="store_true",
        help="禁用筹码因子（chip）评分",
    )
    parser.add_argument(
        "--no-macro",
        action="store_true",
        help="禁用宏观安全垫检查",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="保存本次筛选快照到 data/snapshots/（review#16）",
    )
    parser.add_argument(
        "--two-stage",
        action="store_true",
        help="两阶段管线：Phase 1 无 K 线初筛 → Phase 2 仅对 Top N×3 拉 K 线精排",
    )
    parser.add_argument("-j", "--json", action="store_true")
    parser.add_argument(
        "--brief",
        action="store_true",
        help="简要模式：一句话结论 + 精简表格 + 操作建议",
    )
    return parser


def _default_progress_callback(event, payload):
    """默认 callback：把业务事件转 print（保持原 CLI 输出等价）。"""
    if event == "init":
        # empty_universe
        if payload.get("halted"):
            reason = payload.get("reason", "")
            if reason == "empty_universe":
                print("❌ 股票池为空，无法选股。")
                print()
                print("请先初始化股票池:")
                print("  /screener init          # 联网获取最新数据")
                print("  /screener init default  # 使用预置数据（离线可用）")
            elif reason == "macro_red":
                print("⚠️ 系统性风险，暂停选股", flush=True)
            return
        # market_regime
        regime = payload.get("regime")
        if regime:
            print(f"📊 市场状态: {regime.label} ({regime.value})", flush=True)
        # macro
        macro_msg = payload.get("macro_msg")
        if macro_msg:
            print(macro_msg, flush=True)
    elif event == "phase1":
        print(
            f"⚡ Phase 1: {payload['count_in']} 只 → Top {payload['count_out']} 只 "
            f"({payload['elapsed']:.2f}s)",
            flush=True,
        )
    elif event == "phase2":
        print(
            f"🎯 Phase 2: {payload['count']} 只精排 ({payload['elapsed']:.2f}s)",
            flush=True,
        )
        saved = payload.get("saved_kline", 0)
        if saved:
            print(
                f"✅ 两阶段管线完成: {payload['total']:.2f}s "
                f"(节省 K 线 {saved} 只)",
                flush=True,
            )
    elif event == "snapshot":
        print(f"📸 快照已保存: {payload['path']}", flush=True)


def _run_main(args):
    """main() 核心逻辑（瘦身后：callback + 调用 run_screening + 输出分发）。"""
    # JSON 模式使用静默 callback，避免进度输出混入 JSON
    callback = _default_progress_callback if not args.json else (lambda e, p: None)
    result = run_screening(args, progress_callback=callback)

    if result["halted"]:
        # 宏观 RED 且非 JSON 模式 → 暂停；JSON 模式仍输出空结果
        if not args.json:
            return

    rows = result["rows"]

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        title = None
        if args.full_market:
            title = f"全市场筛选（{args.sector}）" if args.sector else "全市场筛选"
        if args.brief:
            render_brief(rows, args.strategy, args.top, title=title)
        else:
            show_chip = not getattr(args, "no_chip", False)
            render(rows, args.strategy, args.top, title=title, show_chip=show_chip)


def main():
    """CLI 入口：解析参数 + 委托 _run_main。"""
    from common.cache import cleanup_tmp_files

    cleanup_tmp_files()
    parser = _build_parser()
    args = parser.parse_args()
    _run_main(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        from common.exceptions import format_error

        print(f"❌ {format_error(e)}", file=sys.stderr)
        sys.exit(1)
