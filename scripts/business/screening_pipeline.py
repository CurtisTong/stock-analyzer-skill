"""
选股管线编排模块。

提供 run_screening、analyze_code、analyze_code_phase1 等管线编排函数。
从 screening_service.py 拆分，保持所有公开 API 不变。
"""

import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Callable

from common import (
    normalize_finance_code,
    normalize_quote_code,
)
from data.helpers import (
    fetch_finance_first,
    fetch_batch_dicts,
    prefetch_finance_all,
    prefetch_kline_all,
)
from classifier import infer_industry
from strategies import STRATEGIES
from strategies.factors.registry import get_factor_keys

from business.screening_service import (
    ScreeningService,
    AnalyzeContext,
    compute_features,
    compute_factor_parts,
    compute_phase1_parts,
    compute_weighted_score,
    normalize_factors_batch,
    build_result_row,
    ResultRowContext,
)
from business.universe_loader import (
    load_universe,
    pre_screen_quotes,
    apply_portfolio_constraints,
)

logger = logging.getLogger(__name__)

# ScreeningService 模块级缓存：避免循环中重复创建实例
_screening_service_instance = None


def _get_screening_service() -> ScreeningService:
    """获取 ScreeningService 单例（缓存复用，避免循环中重复创建）。"""
    global _screening_service_instance
    if _screening_service_instance is None:
        _screening_service_instance = ScreeningService()
    return _screening_service_instance


def analyze_code(
    quote,
    strategy,
    args,
    finance_cache=None,
    regime=None,
    kline_cache=None,
):
    """分析单只股票（CLI 友好入口，接受 quote dict）。

    委托给 ScreeningService._analyze_stock()，消除重复逻辑。
    """
    code = quote["code"]
    quote_code = normalize_quote_code(code)
    if finance_cache is not None:
        records = finance_cache.get(quote_code, [])
        fin = records[0] if records else {}
    else:
        fin = fetch_finance_first(normalize_finance_code(quote_code))
    # 复用预拉 K 线，避免每只股票独立 get_kline
    if kline_cache is not None and quote_code in kline_cache:
        kline_bars = kline_cache[quote_code]
    else:
        kline_bars = None

    filters = {
        "min_amount": args.min_amount,
        "min_cap": args.min_cap,
        "exclude_loss": args.exclude_loss,
    }
    ctx = AnalyzeContext(
        code=quote_code,
        quote=quote,
        fin_records=[fin] if fin else [],
        strategy=strategy,
        filters=filters,
        kline_bars=kline_bars,
        phase1=True,
        regime=regime,
        no_chip=getattr(args, "no_chip", False),
    )
    return _get_screening_service()._analyze_stock(ctx)


def analyze_code_phase1(quote, args, finance_cache=None, regime=None):
    """Phase 1：仅算 quality/valuation/liquidity/chip（不依赖 K 线）。"""
    code = quote["code"]
    quote_code = normalize_quote_code(code)
    if finance_cache is not None:
        records = finance_cache.get(quote_code, [])
        fin = records[0] if records else {}
    else:
        fin = fetch_finance_first(normalize_finance_code(quote_code))

    filters = {
        "min_amount": args.min_amount,
        "min_cap": args.min_cap,
        "exclude_loss": args.exclude_loss,
    }
    svc = _get_screening_service()
    rejected = svc._hard_filter(quote, fin, filters)
    industry = infer_industry(
        quote.get("name", ""), quote_code, fetcher_industry=quote.get("industry", "")
    )
    parts = compute_phase1_parts(fin, quote, industry)
    if getattr(args, "no_chip", False):
        parts["chip"] = 50
    total = compute_weighted_score(parts, args.strategy, regime=regime)
    return build_result_row(
        ResultRowContext(
            code=quote_code,
            quote_dict=quote,
            fin=fin,
            features={
                "ret20": 0,
                "rsi": 50,
                "macd_signal": 0,
                "vol_price_signal": 0,
                "trend": 0,
            },
            industry=industry,
            total=total,
            parts=parts,
            rejected=rejected,
        )
    )


def _apply_factor_normalization(rows, strategy, regime=None):
    """对所有候选股的因子做 z-score 标准化并重新计算 score。"""
    valid_rows = [r for r in rows if not r.get("rejected")]
    if len(valid_rows) < 3:
        return
    keys = get_factor_keys()  # 从注册表自动获取，与 normalize_factors_batch 同步
    parts_list = [{k: r.get(k, 0) for k in keys} for r in valid_rows]
    normed = normalize_factors_batch(parts_list)
    for row, n in zip(valid_rows, normed):
        for k in keys:
            row[k] = round(n[k], 1)
        row["score"] = round(compute_weighted_score(n, strategy, regime=regime), 1)


def run_screening(args, progress_callback: Optional[Callable] = None) -> dict:
    """选股管线编排（业务层，与 CLI 输出解耦）。

    Args:
        args: CLI Namespace
        progress_callback: 可选回调，签名 callback(event: str, payload: dict) -> none。
            事件类型：init / phase1 / phase2 / snapshot

    Returns:
        dict: {rows, regime, macro_state, phase_stats, snapshot_path, halted}
    """
    import time as _time

    def _cb(event, payload=None):
        if progress_callback:
            progress_callback(event, payload or {})

    codes = load_universe(args)
    if not codes:
        _cb("init", {"halted": True, "reason": "empty_universe"})
        return {
            "rows": [],
            "regime": None,
            "macro_state": None,
            "phase_stats": {},
            "snapshot_path": None,
            "halted": True,
        }

    t_pipeline_start = _time.perf_counter()
    phase_stats = {}

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_quotes = ex.submit(fetch_batch_dicts, codes)
        f_finance = ex.submit(prefetch_finance_all, codes)
        quotes = f_quotes.result()

    if args.full_market:
        quotes = pre_screen_quotes(quotes, args)

    finance_cache = f_finance.result()
    finance_cache = {normalize_quote_code(code): v for code, v in finance_cache.items()}

    # 市场状态检测
    regime = None
    if not args.no_regime:
        try:
            from strategies.regime import detect_signals, classify_regime

            signals = detect_signals()
            regime = classify_regime(signals)
            _cb("init", {"regime": regime})
        except Exception as e:
            print(f"⚠️ 市场状态检测失败: {e}", file=sys.stderr)
            regime = None

    # 宏观安全垫检查
    macro_state = None
    if not getattr(args, "no_macro", False):
        try:
            from strategies.macro import MacroSafetyGate

            gate = MacroSafetyGate()
            macro_state, macro_msg = gate.check()
            _cb("init", {"macro_msg": macro_msg, "macro_state": macro_state})
            if macro_state.value == "RED":
                _cb("init", {"halted": True, "reason": "macro_red"})
                return {
                    "rows": [],
                    "regime": regime,
                    "macro_state": macro_state,
                    "phase_stats": phase_stats,
                    "snapshot_path": None,
                    "halted": True,
                }
        except Exception as e:
            print(f"⚠️ 宏观安全垫检查失败: {e}", file=sys.stderr)
            macro_state = None

    if args.two_stage:
        t_p1 = _time.perf_counter()
        rows_p1 = [
            analyze_code_phase1(q, args, finance_cache, regime=regime) for q in quotes
        ]
        if not args.no_normalize and len(rows_p1) >= 3:
            _apply_factor_normalization(rows_p1, args.strategy, regime=regime)
        # 先配对再排序，避免 sort 后 zip 将 quote 与错误 row 配对
        pairs = list(zip(quotes, rows_p1))
        pairs.sort(key=lambda qr: qr[1].get("score", 0), reverse=True)
        top_n_phase2 = max(args.top * 3, 10)
        top_quotes = [q for q, r in pairs if r.get("score", 0) > 0][:top_n_phase2]
        t_p1 = _time.perf_counter() - t_p1
        _cb(
            "phase1",
            {"count_in": len(quotes), "count_out": len(top_quotes), "elapsed": t_p1},
        )

        t_p2 = _time.perf_counter()
        kline_cache = prefetch_kline_all([q["code"] for q in top_quotes])
        rows = [
            analyze_code(
                q,
                args.strategy,
                args,
                finance_cache,
                regime=regime,
                kline_cache=kline_cache,
            )
            for q in top_quotes
        ]
        if not args.no_normalize and len(rows) >= 3:
            _apply_factor_normalization(rows, args.strategy, regime=regime)
        t_p2 = _time.perf_counter() - t_p2
        t_total = _time.perf_counter() - t_pipeline_start
        phase_stats = {
            "p1_elapsed": t_p1,
            "p2_elapsed": t_p2,
            "total": t_total,
            "saved_kline": len(quotes) - len(top_quotes),
        }
        _cb(
            "phase2",
            {
                "count": len(rows),
                "elapsed": t_p2,
                "total": t_total,
                "saved_kline": len(quotes) - len(top_quotes),
            },
        )
    else:
        kline_cache = prefetch_kline_all([q["code"] for q in quotes])
        rows = [
            analyze_code(
                q,
                args.strategy,
                args,
                finance_cache,
                regime=regime,
                kline_cache=kline_cache,
            )
            for q in quotes
        ]
        if not args.no_normalize and len(rows) >= 3:
            _apply_factor_normalization(rows, args.strategy, regime=regime)
        t_total = _time.perf_counter() - t_pipeline_start
        _cb("phase2", {"count": len(rows), "elapsed": t_total, "total": t_total})

    rows.sort(key=lambda r: r["score"], reverse=True)

    if not args.no_constraints:
        rows = apply_portfolio_constraints(rows, sector_cap=args.sector_cap)

    snapshot_path = None
    if args.snapshot:
        try:
            from snapshots import save_snapshot

            snapshot_path = save_snapshot(
                strategy=args.strategy,
                rows=rows,
                codes=[q["code"] for q in quotes],
                regime=regime.value if regime else None,
            )
            _cb("snapshot", {"path": snapshot_path})
        except Exception as e:
            print(f"⚠️ 快照保存失败: {e}", file=sys.stderr)

    return {
        "rows": rows,
        "regime": regime,
        "macro_state": macro_state,
        "phase_stats": phase_stats,
        "snapshot_path": snapshot_path,
        "halted": False,
    }
