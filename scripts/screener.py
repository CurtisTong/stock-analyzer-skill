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
from concurrent.futures import as_completed
from pathlib import Path

from common import (
    DATA_DIR,
    board_type,
    clamp,
    get_shared_executor,
    normalize_finance_code,
    normalize_quote_code,
    plain_code,
    to_float,
)
from data import get_quote, get_quotes, get_kline, get_finance
from data.helpers import (
    fetch_quote_dict,
    fetch_batch_dicts,
    fetch_kline_dicts,
    fetch_finance_dicts,
)
from classifier import infer_industry
from strategies import (
    STRATEGIES,
    quality_score,
    valuation_score,
    momentum_score,
    liquidity_score,
    volatility_from_closes,
    dividend_score,
)
from strategies.thresholds import get_industry_threshold, load_industry_thresholds
from technical.volume import volume_analysis
from business.screening_service import (
    compute_features,
    compute_factor_parts,
    compute_weighted_score,
    normalize_factors_batch,
    build_result_row,
)

# ---------- 数据层适配函数（委托给 data.helpers） ----------


def _fetch_quote_dict(code: str) -> dict:
    """获取单只行情，返回 dict（兼容旧接口）。

    测试桩点（test seam）：测试通过 monkeypatch 替换此函数隔离网络依赖。
    """
    return fetch_quote_dict(normalize_quote_code(code))


def _fetch_batch_dicts(codes: list) -> list:
    """批量获取行情，返回 dict 列表。

    测试桩点（test seam）：测试通过 monkeypatch 替换此函数隔离网络依赖。
    """
    return fetch_batch_dicts(codes)


def _fetch_kline_dicts(code: str, limit: int = 240, scale: int = 30) -> list:
    """获取 K 线，返回 dict 列表。

    测试桩点（test seam）：测试通过 monkeypatch 替换此函数隔离网络依赖。
    """
    return fetch_kline_dicts(normalize_quote_code(code), scale=scale, datalen=limit)


def _fetch_finance_dicts(code: str) -> list:
    """获取财务数据，返回 dict 列表。

    测试桩点（test seam）：测试通过 monkeypatch 替换此函数隔离网络依赖。
    """
    return fetch_finance_dicts(normalize_finance_code(code))


# board_type() 返回值 → all_stocks.json 中的键名映射
# board_type() 返回 "主板"，但 all_stocks.json 按上市板块分为 "主板沪" 和 "主板深"
_BOARD_KEY_MAP = {
    "主板": ["主板沪", "主板深"],
    "创业板": ["创业板"],
    "科创板": ["科创板"],
    "北交所": ["北交所"],
}


def load_full_market_universe(boards=None):
    """从 data/all_stocks.json 加载全市场股票池。

    Args:
        boards: 可选，指定板块列表（使用 board_type() 的返回值，如 ["主板", "创业板"]）。
                "主板" 会自动匹配 "主板沪" + "主板深"。
                None 表示加载全部板块。
    Returns:
        list[str] — 股票代码列表
    """
    path = DATA_DIR / "all_stocks.json"
    if not path.exists():
        raise SystemExit(
            "data/all_stocks.json 不存在，请先运行:\n"
            "  python3 scripts/refresh_pool.py --full-market"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    # 过滤掉 _meta 等非板块键
    all_board_keys = [k for k in data if not k.startswith("_")]
    if boards:
        # 通过显式映射将 board_type() 返回值转换为 all_stocks.json 的键名
        target_keys = []
        for b in boards:
            target_keys.extend(_BOARD_KEY_MAP.get(b, [b]))
        board_keys = [k for k in all_board_keys if k in target_keys]
        if not board_keys:
            raise SystemExit(f"未在 all_stocks.json 找到板块: {boards}")
    else:
        board_keys = all_board_keys
    all_codes = []
    for key in board_keys:
        all_codes.extend(data.get(key, []))
    return sorted({normalize_quote_code(c) for c in all_codes})


# 预筛选阈值（v1.7.1 起统一从 strategies.filters 导入，消除与 refresh_pool 的隐式耦合）
from strategies.filters import PRE_SCREEN_FILTER as _PRE_SCREEN


def pre_screen_quotes(quotes, args):
    """全市场模式预筛选：排除 ST / 停牌 / 低流动性 / 低市值股票。

    Args:
        quotes: _fetch_batch_dicts 返回的 dict 列表
        args: CLI 参数（读取 board_limit）
    Returns:
        过滤后的 dict 列表
    """
    before = len(quotes)
    result = []
    for q in quotes:
        name = q.get("name", "")
        # 排除 ST
        if "ST" in name.upper():
            continue
        # 排除停牌 / 无成交（amount 单位为元）
        amount_yuan = to_float(q.get("amount", 0))
        if amount_yuan <= 0:
            continue
        # 板块判断
        bt = board_type(q.get("code", ""))
        if bt == "其他":
            continue
        # 成交额过滤（阈值万元 → 元）
        min_amt = _PRE_SCREEN["min_amount"].get(bt, 5000) * 10000
        if amount_yuan < min_amt:
            continue
        # 总市值过滤（total_cap 单位亿）
        cap = to_float(q.get("total_cap", 0))
        min_cap = _PRE_SCREEN["min_cap"].get(bt, 40)
        if cap < min_cap:
            continue
        result.append(q)

    # 按板块截取（每板块最多 N 只，按成交额降序）
    board_limit = getattr(args, "board_limit", 0)
    if board_limit > 0:
        from collections import defaultdict

        buckets = defaultdict(list)
        for q in result:
            buckets[board_type(q.get("code", ""))].append(q)
        result = []
        for stocks in buckets.values():
            stocks.sort(key=lambda x: to_float(x.get("amount", 0)), reverse=True)
            result.extend(stocks[:board_limit])

    after = len(result)
    print(f"全市场预筛选: {before} → {after} 只（排除 ST/停牌/低流动性/低市值）")
    return result


def load_universe(args):
    codes = args.codes.split(",") if args.codes else None
    if codes:
        return sorted({normalize_quote_code(c) for c in codes})

    # 全市场模式
    if args.full_market:
        boards = [args.sector] if args.sector else None
        all_codes = load_full_market_universe(boards)

        # 排除指定板块
        if args.exclude_board:
            exclude_boards = [b.strip() for b in args.exclude_board.split(",")]
            filtered = []
            for code in all_codes:
                bt = board_type(code)
                if bt not in exclude_boards:
                    filtered.append(code)
            return sorted(filtered)

        return all_codes

    # 现有板块模式
    sector = args.sector
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
                print(
                    f"📡 动态获取板块 '{name}' ({', '.join(bk_codes)})...", flush=True
                )
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
    return {
        "signal": result.get("volume_price_signal", 0),
        "desc": result.get("volume_price", "量价中性"),
    }


def _apply_factor_normalization(rows, strategy, regime=None):
    """对所有候选股的 6 因子做 z-score 标准化并重新计算 score。

    解决问题（review#14）：六因子评分范围差异巨大（quality 30-85, volatility 5-95），
    不加标准化导致 volatility 因子隐式权重超调。

    Args:
        rows: analyze_code 输出的候选股列表（含 quality/valuation/momentum/liquidity/volatility/dividend 字段）
        strategy: 策略名
        regime: 市场状态枚举（可选；如传入则加权时应用 overlay）
    """
    from business.screening_service import compute_weighted_score

    valid_rows = [r for r in rows if not r.get("rejected")]
    if len(valid_rows) < 3:
        return
    keys = ("quality", "valuation", "momentum", "liquidity", "volatility", "dividend")
    parts_list = [{k: r.get(k, 0) for k in keys} for r in valid_rows]
    normed = normalize_factors_batch(parts_list)
    for row, n in zip(valid_rows, normed):
        for k in keys:
            row[k] = round(n[k], 1)
        row["score"] = round(compute_weighted_score(n, strategy, regime=regime), 1)


def daily_features(code):
    """计算技术指标特征（复用 business 层 compute_features，消除重复计算）。"""
    return compute_features(code)


def hard_filter(quote, fin, args):
    """硬过滤（v1.3.1 委托给 ScreeningService 业务层）。"""
    from business.screening_service import ScreeningService

    filters = {
        "min_amount": args.min_amount,
        "min_cap": args.min_cap,
        "exclude_loss": args.exclude_loss,
    }
    return ScreeningService()._hard_filter(quote, fin, filters)


def prefetch_finance_all(codes):
    """并发拉取所有股票的财务数据。"""
    results = {}

    def _fetch_one(code):
        # data 层已有零值缓存校验，自动跳过无效缓存
        from data import get_finance

        records = get_finance(normalize_finance_code(code))
        return code, [r.to_dict() for r in records]

    ex = get_shared_executor()
    futures = {ex.submit(_fetch_one, c): c for c in codes}
    for future in as_completed(futures):
        try:
            code, data = future.result()
            results[code] = data
        except Exception:
            results[futures[future]] = []
    return results


def _prefetch_kline_all(codes, scale: int = 240, datalen: int = 240):
    """review#12：批量预拉 K 线。返回 {code: KlineBar列表}。

    使用 parallel_fetch_dict 并发拉取（cache hit 时仍并发处理，避免串行磁盘 IO）。
    K 线 TTL 6 小时，同一回测/筛选周期内同 code 仅首次真实请求。
    """
    from data import get_kline
    from common import parallel_fetch_dict

    def _fetch_one(code):
        return get_kline(normalize_quote_code(code), scale=scale, datalen=datalen)

    return parallel_fetch_dict(codes, _fetch_one, label="screener:kline")


def analyze_code_phase1(quote, args, finance_cache=None, regime=None):
    """Sprint 9 Phase 1：仅算 quality/valuation/liquidity（不依赖 K 线）。

    用于全市场初筛，3-5 秒内完成 5000 只股票评分。
    """
    code = quote["code"]
    quote_code = normalize_quote_code(code)
    if finance_cache is not None:
        records = finance_cache.get(quote_code, [])
        fin = records[0] if records else {}
    else:
        fin = latest_finance(quote_code)
    rejected = hard_filter(quote, fin, args)

    industry = infer_industry(
        quote.get("name", ""), quote_code, fetcher_industry=quote.get("industry", "")
    )
    from business.screening_service import (
        compute_phase1_parts, compute_weighted_score,
    )
    parts = compute_phase1_parts(fin, quote, industry)
    total = compute_weighted_score(parts, args.strategy, regime=regime)
    return build_result_row(
        quote_code, quote, fin, {"ret20": 0, "rsi": 50, "macd_signal": 0,
                                  "vol_price_signal": 0, "trend": 0},
        industry, total, parts, rejected,
    )


def analyze_code(quote, strategy, args, finance_cache=None, regime=None, kline_cache=None):
    code = quote["code"]
    quote_code = normalize_quote_code(code)
    if finance_cache is not None:
        records = finance_cache.get(quote_code, [])
        fin = records[0] if records else {}
    else:
        fin = latest_finance(quote_code)
    # review#12 修复：复用预拉的 K 线，避免每只股票独立 get_kline 调用
    if kline_cache is not None and quote_code in kline_cache:
        from business.screening_service import compute_features
        features = compute_features(quote_code, bars=kline_cache[quote_code])
    else:
        features = daily_features(quote_code)
    rejected = hard_filter(quote, fin, args)

    # 推断行业，获取行业差异化阈值
    industry = infer_industry(
        quote.get("name", ""), quote_code, fetcher_industry=quote.get("industry", "")
    )
    parts = compute_factor_parts(fin, quote, features, industry)

    # 两阶段策略：Stage 1 硬条件过滤（review#2）
    from strategies import STRATEGIES as _STRATS
    if _STRATS.get(strategy, {}).get("two_stage"):
        from strategies.filters.turning_point import turning_point_filter
        pass_, reason = turning_point_filter(quote, fin, features)
        if not pass_:
            rejected = list(rejected) + [f"未通过拐点过滤: {reason}"]
            return build_result_row(
                quote_code, quote, fin, features, industry,
                0, parts, rejected,
            )

    total = compute_weighted_score(parts, strategy, regime=regime)
    return build_result_row(
        quote_code, quote, fin, features, industry, total, parts, rejected
    )


def apply_portfolio_constraints(
    rows: list, sector_cap: float = 0.30, trend_penalty: float = 0.70
) -> list:
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

    # review#15 修复：候选池 < 10 时不强制板块集中度（避免 5 只池被压成 1 只/行业）
    min_pool_for_sector_cap = 10
    if len(rows) >= min_pool_for_sector_cap:
        max_per_sector = max(2, int(len(rows) * sector_cap))
    else:
        max_per_sector = len(rows)  # 不限制

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


def render(rows, strategy, top, title=None):
    accepted = [r for r in rows if not r["rejected"]]
    rejected = [r for r in rows if r["rejected"]]
    accepted.sort(key=lambda r: r["score"], reverse=True)

    label = title or STRATEGIES[strategy]["label"]
    print(f"策略: {label} ({strategy})")
    print(f"入选: {len(accepted)} | 剔除: {len(rejected)}")
    print()
    header = "排名 | 代码 | 名称 | 行业 | 板块 | 总分 | 质量 | 估值 | 动量 | 流动性 | PE | ROE | RSI | 20日% | 趋势 | 量价"
    print(header)
    print("-" * len(header))
    for idx, r in enumerate(accepted[:top], 1):
        macd_icon = (
            "↑"
            if r.get("macd_signal", 0) > 0
            else "↓" if r.get("macd_signal", 0) < 0 else "→"
        )
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


def _build_parser():
    """构造 screener CLI 参数解析器（V2.1 提取便于单测复用）。"""
    parser = argparse.ArgumentParser(description="A 股多因子选股器", add_help=False)
    from common.version import __version__
    parser.add_argument("-v", "--version", action="version", version=f"screener {__version__}")
    parser.add_argument("-h", "--help", action="help", help="显示帮助")
    parser.add_argument("--strategy", choices=STRATEGIES.keys(), default="balanced")
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
    return parser


def _run_main(args):
    """main() 核心逻辑（V2.1 提取便于单测）。"""
    codes = load_universe(args)

    # review#11 修复：行情与财务数据并行拉取（原来串行，总耗时 = sum）
    from concurrent.futures import ThreadPoolExecutor
    import time as _time

    t_pipeline_start = _time.perf_counter()

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_quotes = ex.submit(_fetch_batch_dicts, codes)
        # 财务拉取依赖 codes 不依赖 quotes，所以也可以同时启动
        f_finance = ex.submit(prefetch_finance_all, codes)
        quotes = f_quotes.result()

    # 全市场模式预筛选（大幅减少进入六因子分析的股票数量）
    if args.full_market:
        quotes = pre_screen_quotes(quotes, args)

    finance_cache = f_finance.result()
    # 财务缓存 key 是 normalize 后的代码，确保与 quote code 一致
    finance_cache = {
        normalize_quote_code(code): v for code, v in finance_cache.items()
    }

    # 市场状态检测（Sprint 2 / doc#03）：4 信号 + 4 状态 + 6 因子 overlay
    regime = None
    if not args.no_regime:
        try:
            from strategies.regime import detect_signals, classify_regime
            signals = detect_signals()
            regime = classify_regime(signals)
            print(f"📊 市场状态: {regime.label} ({regime.value})", flush=True)
        except Exception as e:
            print(f"⚠️ 市场状态检测失败: {e}", file=sys.stderr)
            regime = None

    # Sprint 9 两阶段管线：Phase 1（无 K 线初筛）→ Phase 2（K 线精排）
    # 全市场模式下显著降低 K 线获取量（5000 → top×3）
    if args.two_stage:
        t_p1 = _time.perf_counter()
        rows_p1 = [
            analyze_code_phase1(q, args, finance_cache, regime=regime)
            for q in quotes
        ]
        # z-score 标准化仅在 Phase 1 维度（quality/valuation/liquidity）
        if not args.no_normalize and len(rows_p1) >= 3:
            _apply_factor_normalization(rows_p1, args.strategy, regime=regime)
        # 按分数排序，取 Top N×3 进入 Phase 2
        rows_p1.sort(key=lambda r: r.get("score", 0), reverse=True)
        top_n_phase2 = max(args.top * 3, 10)
        top_quotes = [q for q, r in zip(quotes, rows_p1) if r.get("score", 0) > 0][:top_n_phase2]
        # 复用 rows_p1 中前 top_n_phase2 行的元数据
        rows_p1_top = rows_p1[: len(top_quotes)]
        t_p1 = _time.perf_counter() - t_p1
        print(
            f"⚡ Phase 1: {len(quotes)} 只 → Top {len(top_quotes)} 只 ({t_p1:.2f}s)",
            flush=True,
        )

        # Phase 2：仅对 Top N×3 拉 K 线，算 momentum/volatility/dividend
        t_p2 = _time.perf_counter()
        kline_cache = _prefetch_kline_all([q["code"] for q in top_quotes])
        rows = [
            analyze_code(q, args.strategy, args, finance_cache, regime=regime, kline_cache=kline_cache)
            for q in top_quotes
        ]
        if not args.no_normalize and len(rows) >= 3:
            _apply_factor_normalization(rows, args.strategy, regime=regime)
        t_p2 = _time.perf_counter() - t_p2
        print(
            f"🎯 Phase 2: {len(rows)} 只精排 ({t_p2:.2f}s)",
            flush=True,
        )
        t_total = _time.perf_counter() - t_pipeline_start
        print(
            f"✅ 两阶段管线完成: {t_total:.2f}s "
            f"(节省 K 线 {len(quotes) - len(top_quotes)} 只)",
            flush=True,
        )
    else:
        # 单阶段（原行为）：一次性拉所有 K 线 + 算 6 因子
        kline_cache = _prefetch_kline_all([q["code"] for q in quotes])
        rows = [
            analyze_code(q, args.strategy, args, finance_cache, regime=regime, kline_cache=kline_cache)
            for q in quotes
        ]
        if not args.no_normalize and len(rows) >= 3:
            _apply_factor_normalization(rows, args.strategy, regime=regime)

    rows.sort(key=lambda r: r["score"], reverse=True)

    # 应用组合约束（除非禁用）
    if not args.no_constraints:
        rows = apply_portfolio_constraints(rows, sector_cap=args.sector_cap)

    # Sprint 5 / review#16：保存选股快照（默认关闭，--snapshot 开启）
    if args.snapshot:
        try:
            from snapshots import save_snapshot
            path = save_snapshot(
                strategy=args.strategy,
                rows=rows,
                codes=[q["code"] for q in quotes],
                regime=regime.value if regime else None,
            )
            print(f"📸 快照已保存: {path}", flush=True)
        except Exception as e:
            print(f"⚠️ 快照保存失败: {e}", file=sys.stderr)

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        title = None
        if args.full_market:
            title = f"全市场筛选（{args.sector}）" if args.sector else "全市场筛选"
        render(rows, args.strategy, args.top, title=title)


def main():
    """CLI 入口：解析参数 + 委托 _run_main。"""
    from common.cache import cleanup_tmp_files

    cleanup_tmp_files()
    parser = _build_parser()
    args = parser.parse_args()
    _run_main(args)


if __name__ == "__main__":
    main()
