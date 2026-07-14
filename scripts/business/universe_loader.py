"""
股票池加载模块。

提供全市场/板块/自选股票池加载，以及预筛选和组合约束。
从 screening_service.py 拆分，保持所有公开 API 不变。
"""

import json
import logging
import sys
from typing import List, Dict, Any, Optional

from common import (
    board_type,
    normalize_quote_code,
    to_float,
)
from common.utils import (
    DATA_DIR as _DATA_DIR,
)  # noqa: E402 — 延迟引用，支持 monkeypatch


def _get_data_dir():
    """获取数据目录（支持 monkeypatch 替换）。

    测试通过 monkeypatch 本模块的 DATA_DIR 属性来替换数据目录，
    因此需要通过函数调用获取当前值而非在模块加载时固定。
    """
    # 优先使用本模块属性（monkeypatch 目标），回退到原始导入值
    return globals().get("DATA_DIR", _DATA_DIR)


# 允许 monkeypatch 替换的模块级属性
DATA_DIR = _DATA_DIR
from strategies.filters import PRE_SCREEN_FILTER as _PRE_SCREEN

logger = logging.getLogger(__name__)

# board_type() 返回值 → all_stocks.json 中的键名映射
# board_type() 返回 "主板"，但 all_stocks.json 按上市板块分为 "主板沪" 和 "主板深"
_BOARD_KEY_MAP = {
    "主板": ["主板沪", "主板深"],
    "创业板": ["创业板"],
    "科创板": ["科创板"],
    "北交所": ["北交所"],
}


def load_full_market_universe(boards=None):
    """从 data/all_stocks.json 加载全市场股票池。"""
    path = _get_data_dir() / "all_stocks.json"
    if not path.exists():
        raise SystemExit(
            "data/all_stocks.json 不存在，请先运行:\n"
            "  python3 scripts/refresh_pool.py --full-market"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    all_board_keys = [k for k in data if not k.startswith("_")]
    if boards:
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


def _try_fetch_from_mapping(sector: str) -> list:
    """从 sector_mapping.json 查找板块的 BK 代码，动态拉取成分股。"""
    mapping_path = _get_data_dir() / "sector_mapping.json"
    if not mapping_path.exists():
        return []
    try:
        from refresh_pool import fetch_multiple_boards, build_sector_pool

        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
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


def load_universe(args):
    """加载股票池（codes / full_market / sector 三种模式）。"""
    codes = args.codes.split(",") if args.codes else None
    if codes:
        return sorted({normalize_quote_code(c) for c in codes})

    if args.full_market:
        boards = [args.sector] if args.sector else None
        all_codes = load_full_market_universe(boards)
        if args.exclude_board:
            exclude_boards = [b.strip() for b in args.exclude_board.split(",")]
            filtered = []
            for code in all_codes:
                bt = board_type(code)
                if bt not in exclude_boards:
                    filtered.append(code)
            return sorted(filtered)
        return all_codes

    sector = args.sector
    path = _get_data_dir() / "sector_stocks.json"
    sectors = json.loads(path.read_text(encoding="utf-8"))
    if sector:
        matched = []
        for name, items in sectors.items():
            if sector.lower() in name.lower():
                matched.extend(items)
        if not matched:
            matched = _try_fetch_from_mapping(sector)
        if not matched:
            raise SystemExit(f"未在内置标的库找到板块: {sector}")
        return sorted({normalize_quote_code(c) for c in matched})

    all_codes = []
    for items in sectors.values():
        all_codes.extend(items)
    return sorted({normalize_quote_code(c) for c in all_codes})


def pre_screen_quotes(quotes, args):
    """全市场模式预筛选：排除 ST / 停牌 / 低流动性 / 低市值股票 + 用户 blacklist。

    v2.x (#1)：引入自适应流动性阈值。成交额/市值门槛跟随全市场水位动态调整，
    避免缩量时过度瘦身、亢奋时保留过多跟风股。
    动态阈值 = clamp(全市场水位 × ratio, 板块绝对值下限, 板块绝对值 × 倍数上限)
    market_ref 缺失时回退板块绝对值阈值（向后兼容）。
    """
    before = len(quotes)

    # v2.4.0：加载用户偏好（blacklist / sector_exclusions）
    user_blacklist: set = set()
    try:
        from common.user_profile import get_user_preference

        user_blacklist = set(get_user_preference("blacklist") or [])
    except Exception:
        user_blacklist = set()

    # (#1) 获取全市场水位快照（缓存 1 小时，缺失时全 0 -> 回退绝对值）
    market_ref = {"avg_amount_yuan": 0.0, "median_cap": 0.0}
    try:
        from data.market_snapshot import get_market_snapshot

        snap = get_market_snapshot()
        market_ref["avg_amount_yuan"] = snap.get("avg_amount_yuan", 0.0)
        market_ref["median_cap"] = snap.get("median_cap", 0.0)
    except Exception:
        pass  # 快照不可用时回退绝对值，不阻断预筛选

    from strategies.filters import adaptive_amount_threshold, adaptive_cap_threshold

    result = []
    for q in quotes:
        name = q.get("name", "")
        code = q.get("code", "")
        # P1-22: 统一调用 data.pool.is_st，避免与 screening_service 双轨实现
        from data.pool import is_st

        if is_st(name):
            continue
        # v2.4.0：用户自定义 blacklist
        if code and code.lower() in {c.lower() for c in user_blacklist}:
            continue
        amount_yuan = to_float(q.get("amount", 0))
        if amount_yuan <= 0:
            continue
        bt = board_type(q.get("code", ""))
        if bt == "其他":
            continue
        # (#1) 自适应成交额阈值
        min_amt = adaptive_amount_threshold(bt, market_ref["avg_amount_yuan"])
        if amount_yuan < min_amt:
            continue
        cap = to_float(q.get("total_cap", 0))
        # (#1) 自适应市值阈值
        min_cap = adaptive_cap_threshold(bt, market_ref["median_cap"])
        if cap < min_cap:
            continue
        result.append(q)

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
    # (#1) 日志显示动态水位信息，便于调试
    if market_ref["avg_amount_yuan"] > 0:
        print(
            f"全市场预筛选: {before} -> {after} 只"
            f"（市场水位: 日均成交额 {market_ref['avg_amount_yuan']/1e8:.0f}亿 / 中位市值 {market_ref['median_cap']:.0f}亿）"
        )
    else:
        print(f"全市场预筛选: {before} -> {after} 只（排除 ST/停牌/低流动性/低市值）")
    return result


def apply_portfolio_constraints(
    rows: list,
    sector_cap: float = 0.30,
    trend_penalty: float = 0.70,
    benchmark_weights: dict = None,
    use_benchmark_align: bool = False,
    max_deviation: float = 0.15,
) -> list:
    """应用组合层面约束。

    v2.x (#9) 新增行业偏离约束：
    - 当 use_benchmark_align=True 且提供 benchmark_weights 时，
      组合中每个行业的权重不允许偏离基准 ±max_deviation（绝对值差）
    - 候选池 < 20 只时自动关闭偏离约束（避免过度瘦身）

    注意：返回新列表，不修改输入 rows（避免副作用）。
    """
    if not rows:
        return rows

    min_pool_for_sector_cap = 10
    if len(rows) >= min_pool_for_sector_cap:
        max_per_sector = max(2, int(len(rows) * sector_cap))
    else:
        max_per_sector = len(rows)

    # (#9) 行业偏离约束：候选池 >= 20 且启用时生效
    benchmark_active = (
        use_benchmark_align
        and benchmark_weights
        and len(rows) >= 20
    )
    # 基准行业权重归一化（确保和为 1.0）
    if benchmark_active:
        total_bw = sum(benchmark_weights.values())
        norm_benchmark = (
            {k: v / total_bw for k, v in benchmark_weights.items()}
            if total_bw > 0
            else {}
        )
    else:
        norm_benchmark = {}

    sector_count = {}
    result = []
    total_added = 0
    for stock in rows:
        industry = stock.get("industry", "默认")
        if sector_count.get(industry, 0) >= max_per_sector:
            continue

        # (#9) 行业偏离检查：当前行业占比 - 基准占比 > max_deviation 时跳过
        if benchmark_active and industry in norm_benchmark:
            current_pct = sector_count.get(industry, 0) / max(len(rows), 1)
            benchmark_pct = norm_benchmark[industry]
            if current_pct - benchmark_pct > max_deviation:
                continue

        # 深拷贝避免修改原始 rows
        entry = dict(stock)
        if entry.get("trend") == "下降":
            entry["score"] = round(entry["score"] * trend_penalty, 1)
        sector_count[industry] = sector_count.get(industry, 0) + 1
        total_added += 1
        result.append(entry)

    result.sort(key=lambda r: r["score"], reverse=True)
    return result


def load_benchmark_industry_weights() -> dict:
    """(#9) 加载 CSI300 基准行业权重。

    Returns:
        {industry: weight} dict，文件缺失时返回空 dict。
    """
    import json

    path = _get_data_dir() / "csi300_industry_weights.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("weights", {})
    except Exception:
        return {}
