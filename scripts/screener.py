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

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json

from common import normalize_quote_code
from common.cli_base import handle_errors
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
        # P1-02c: 退潮板块高分标的加 ⚠️ 标记
        if r.get("sector_momentum_warning"):
            print(f"  ⚠️ {r['sector_momentum_warning']}")

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
    # v1.x: 改为原始池大小，让"总输入"反映真实漏斗
    total = len(rows)

    # 一句话结论
    if not top_rows:
        print(
            f"策略 {label}: 无符合条件标的（候选池 {total} 只，剔除 {len(rejected)} 只）"
        )
        print()
        print("可能原因:")
        print("  1. 股票池未初始化 → 运行 /screener init 或 /screener init default")
        print("  2. 筛选条件过严 → 尝试其他策略（如 balanced）或加 --board-strict")
        print("  3. 市场休市无数据 → 交易时段重试")
        # 列出剔除原因TOP3
        _print_reject_reasons(rejected)
        return
    best = top_rows[0]
    # v1.x: 三段式漏斗（候选池 → 硬过滤 → 显示 Top），让"总输入"反映真实漏斗
    print(
        f"策略 {label} | 📦 候选池 {total} → 硬过滤后 {len(accepted)} → 显示 Top {len(top_rows)} | "
        f"硬过滤剔除 {len(rejected)} | 首选 {best['code']} {best['name']} (评分 {best['score']})"
    )
    _print_reject_reasons(rejected)

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
        # P1-02c: 退潮板块高分标的加 ⚠️ 标记
        if r.get("sector_momentum_warning"):
            print(f"  ⚠️ {r['sector_momentum_warning']}")

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


def _print_reject_reasons(rejected):
    """汇总硬过滤剔除原因 TOP3，让用户清楚为什么 N 只被砍掉。

    v1.x 改进：解决"请求 top10 却只输出 2"的用户疑惑。
    """
    if not rejected:
        return
    from collections import Counter

    counter: Counter = Counter()
    for r in rejected:
        # reasons 是 list[str]，每只股票的所有剔除原因
        for reason in r.get("rejected", []):
            # 归一化：去掉括号内的阈值差异，保留主因
            key = reason.split("(")[0].strip()
            counter[key] += 1
    top3 = counter.most_common(3)
    if top3:
        parts = " | ".join(f"{reason}({n}只)" for reason, n in top3)
        print(f"剔除原因TOP3: {parts}")


def _print_mainline_deviation_warning(rows, args):
    """主线偏离警告：候选覆盖今日涨幅前 3 板块不足时输出。

    v1.x 改进：解决 2026-08-08 growth_momentum 输出与今日成长主线偏离却无提示的问题。
    """
    import sys

    accepted = [r for r in rows if not r.get("rejected")]
    if not accepted:
        return
    try:
        from quote import get_quotes
        from sector_etf_strength import _load_sector_etfs
    except Exception:
        return

    # 拉取全部板块 ETF 今日涨跌，按涨幅排序取 top 3
    try:
        etfs_meta = _load_sector_etfs()
        codes = [etf["code"] for etf in etfs_meta if etf.get("code")]
        if not codes:
            return
        quotes = get_quotes(codes)
        quotes_sorted = sorted(quotes, key=lambda q: q.change_pct, reverse=True)
        top3 = quotes_sorted[:3]
        top3_names = [q.name for q in top3 if q.change_pct > 0]
        if not top3_names:
            return

        # 计算候选覆盖：候选股票 industry/board 与 top3 板块名匹配
        accepted_industries = {r.get("industry", "") for r in accepted} | {
            r.get("board", "") for r in accepted
        }
        # 用板块 ETF name → 行业主题关键词做宽松匹配
        covered = 0
        for name in top3_names:
            for kw in (
                "医药",
                "半导体",
                "新能源",
                "光伏",
                "军工",
                "机器人",
                "AI",
                "PCB",
            ):
                if kw in name:
                    if any(kw in ai for ai in accepted_industries):
                        covered += 1
                        break

        if top3_names and covered < max(1, len(top3_names) // 2):
            print(
                f"⚠️ 主线偏离警告: 候选仅覆盖今日涨幅前{len(top3_names)}板块的 {covered}/{len(top3_names)} "
                f"({', '.join(top3_names)})，建议加 --sector 或关注主线龙头",
                file=sys.stderr,
            )
    except Exception:
        # 网络异常不影响主输出
        return


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
        "-q",
        "--quiet",
        action="store_true",
        help="静默模式：禁用进度条输出（仅保留最终结果）",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="完整模式：16 列因子详情（默认为精简模式）",
    )
    # v1.x: 板块模式默认放宽容差，避免主题池 20 只被砍剩 2 只；
    # 用 --board-strict 显式恢复原阈值（全量过滤）。
    parser.add_argument(
        "--board-strict",
        dest="board_strict",
        action="store_true",
        default=False,
        help="板块模式启用严格硬过滤（默认放宽松；--no-board-strict 等价默认行为）",
    )
    parser.add_argument(
        "--no-board-strict",
        dest="board_strict",
        action="store_false",
        help="板块模式放宽硬过滤（默认行为）",
    )
    # v1.20.1: 整体任务级超时（watchdog 兜底）
    # v1.21.0 P1-02: 板块退潮过滤（个股行业映射到行业 ETF，近 5 日跌幅 >5% 剔除）
    parser.add_argument(
        "--exclude-sector-momentum",
        action="store_true",
        help="剔除近 5 日板块 ETF 跌幅超阈值（5%%）的退潮板块标的（否则仅加 sector_momentum_warning 标记）",
    )
    parser.add_argument(
        "--deadline",
        type=float,
        default=None,
        help="整体任务超时秒数（默认 1800s，也可由环境变量 STOCK_SCREENER_DEADLINE 设置）",
    )
    return parser


def _default_progress_callback(event, payload, *, file=None):
    """默认 callback：把业务事件转 print（保持原 CLI 输出等价）。

    Args:
        file: 输出流。JSON 模式下传 sys.stderr，进度不污染 stdout 的 JSON。
    """

    def _p(*a, **k):
        k.setdefault("file", file)
        print(*a, **k)

    if event == "init":
        # empty_universe
        if payload.get("halted"):
            reason = payload.get("reason", "")
            if reason == "empty_universe":
                _p("❌ 股票池为空，无法选股。")
                _p()
                _p("请先初始化股票池:")
                _p("  /screener init          # 联网获取最新数据")
                _p("  /screener init default  # 使用预置数据（离线可用）")
            elif reason == "macro_red":
                _p("⚠️ 系统性风险，暂停选股", flush=True)
            return
        # market_regime
        regime = payload.get("regime")
        if regime:
            _p(f"📊 市场状态: {regime.label} ({regime.value})", flush=True)
            # P2-07: 明确告知用户 overlay 已应用/未应用，避免策略语义被静默改变
            if getattr(payload, "_no_regime", False):
                _p("⚙️ regime overlay 已禁用（使用固定权重）", flush=True)
            else:
                _p(
                    f"⚡ 已应用 {regime.label} regime overlay（--no-regime 可禁用）",
                    flush=True,
                )
        # macro
        macro_msg = payload.get("macro_msg")
        if macro_msg:
            _p(macro_msg, flush=True)
    elif event == "data_prefetch":
        # P0-01 后续: 数据预取阶段进度提示（quote/finance 是 full_market 慢/卡的主战场）
        stage = payload.get("stage")
        if stage == "quote":
            _p(
                f"📡 拉取行情 {payload.get('count', '?')} 只（全市场）...",
                flush=True,
            )
        elif stage == "prescreen":
            _p(
                f"🔍 行情预筛完成: {payload.get('count', '?')} 只，进入财务阶段",
                flush=True,
            )
        elif stage == "finance":
            _p(
                f"📊 拉取财务 Top {payload.get('count', '?')} 只"
                f"（可能 1-8min；数据源挂起时由 watchdog 兜底）...",
                flush=True,
            )
        elif stage == "parallel":
            _p(
                f"📡 并行拉取行情+财务（{payload.get('count', '?')} 只）...",
                flush=True,
            )
        elif stage == "done":
            _p(
                f"✅ 数据预取完成 {payload.get('elapsed', 0):.1f}s",
                flush=True,
            )
    elif event == "phase1":
        _p(
            f"⚡ Phase 1: {payload['count_in']} 只 → Top {payload['count_out']} 只 "
            f"({payload['elapsed']:.2f}s)",
            flush=True,
        )
    elif event == "phase2":
        _p(
            f"🎯 Phase 2: {payload['count']} 只精排 ({payload['elapsed']:.2f}s)",
            flush=True,
        )
        saved = payload.get("saved_kline", 0)
        if saved:
            _p(
                f"✅ 两阶段管线完成: {payload['total']:.2f}s "
                f"(节省 K 线 {saved} 只)",
                flush=True,
            )
    elif event == "snapshot":
        _p(f"📸 快照已保存: {payload['path']}", flush=True)


def _run_main(args):
    """main() 核心逻辑（瘦身后：callback + 调用 run_screening + 输出分发）。"""
    # 进度输出策略：--quiet 全静默；JSON 模式进度走 stderr（不污染 stdout 的 JSON）；
    # 正常模式走 stdout（保持原 CLI 输出等价）
    quiet = getattr(args, "quiet", False)
    if quiet:

        def _noop(event, payload):
            return None

        callback = _noop
    elif args.json:
        from functools import partial

        callback = partial(_default_progress_callback, file=sys.stderr)
    else:
        callback = _default_progress_callback

    # v1.20.1: watchdog 整体任务超时（akshare 永久挂起兜底）
    from common.screener_watchdog import start_watchdog
    from common.exceptions import ScreenerTimeoutError

    deadline_sec = getattr(args, "deadline", None)
    wd = start_watchdog(deadline_sec)
    rows_partial: list = []
    halted = True  # 默认 halted=True, 成功路径覆盖为 False

    try:
        with wd:
            result = run_screening(args, progress_callback=callback)
        # 任务在 deadline 内完成 → 正常路径
        halted = bool(result.get("halted", False))
        rows_partial = result.get("rows") or []
    except KeyboardInterrupt:
        # 用户真按了 Ctrl+C
        print("\n⏹ 已中断", file=sys.stderr)
        sys.exit(130)
        return
    except ScreenerTimeoutError:
        # 业务主动抛 ScreenerTimeoutError 的兜底分支（极少触发）
        print(
            f"\n⚠️ 任务超时（deadline={wd.deadline_sec:.0f}s, "
            f"elapsed={wd.elapsed_sec:.1f}s），"
            f"已返回 {len(rows_partial)} 条部分结果。",
            file=sys.stderr,
            flush=True,
        )
        if args.json:
            print(json.dumps(rows_partial, ensure_ascii=False, indent=2))
        sys.exit(2)
        return  # unreachable but for type-checker

    if halted:
        # 宏观 RED 且非 JSON 模式 → 暂停；JSON 模式仍输出空结果
        if not args.json:
            return

    rows = rows_partial

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        title = None
        if args.full_market:
            title = f"全市场筛选（{args.sector}）" if args.sector else "全市场筛选"
        # v1.x: 在输出前计算主线偏离警告（覆盖今日涨幅前 3 板块不足时提示）
        _print_mainline_deviation_warning(rows, args)
        if args.full:
            show_chip = not getattr(args, "no_chip", False)
            render(rows, args.strategy, args.top, title=title, show_chip=show_chip)
        else:
            render_brief(rows, args.strategy, args.top, title=title)


def main():
    """CLI 入口：解析参数 + 委托 _run_main。"""
    from common.cache import cleanup_tmp_files

    cleanup_tmp_files()
    parser = _build_parser()
    args = parser.parse_args()
    _run_main(args)


if __name__ == "__main__":
    # 全市场模式下并发抓取大量财务数据，akshare/urllib 无超时会因代理
    # 连接挂起（CLOSE_WAIT）导致永久卡死。设全局 socket 超时作为安全网：
    # 单条请求 15s 仍无响应则抛 TimeoutError，由 prefetch 的异常处理置空跳过。
    import os as _os
    import socket as _socket

    # 禁用代理：urllib 会读取系统代理（如 localhost:7897 的 Clash），
    # 代理连接失效时 akshare 请求会挂起。设 NO_PROXY=* 让请求直连。
    _os.environ["NO_PROXY"] = "*"
    _os.environ["no_proxy"] = "*"
    _socket.setdefaulttimeout(15)
    with handle_errors():
        main()
