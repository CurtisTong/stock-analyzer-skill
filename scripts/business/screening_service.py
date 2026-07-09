"""
选股服务 (Business 层)。

提供选股筛选的业务逻辑，与 CLI 层解耦。

拆分说明（v2.3.0）：
- screening_service.py: 核心服务类 ScreeningService + 上下文 dataclass + 辅助函数 + 因子计算
- screening_pipeline.py: 管线编排（run_screening, analyze_code, analyze_code_phase1）
- universe_loader.py: 股票池加载（load_universe, load_full_market_universe, pre_screen_quotes, apply_portfolio_constraints）

所有公开 API 的导入路径保持不变（通过本文件 re-export）。
"""

import logging
from typing import List, Dict, Any, Optional

from common import (
    board_type,
    board_exact_limit_pct,
    get_shared_executor,
    normalize_finance_code,
    normalize_quote_code,
    to_float,
)
from common.exceptions import ValidationError
from common.validators import validate_code
from data import get_quotes, get_kline, get_finance
from data.helpers import (
    fetch_finance_first,
)
from classifier import infer_industry
from strategies import (
    STRATEGIES,
    chip_score_static,
    get_strategy,
)
from strategies.factors.registry import (
    compute_all_factors,
    compute_phase_factors,
    get_factor_keys,
)
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def _limit(key: str, default):
    """读取 limits.yaml 中的阈值；无 config 时回退到硬编码默认。"""
    from config.loader import safe_get

    return safe_get("limits.yaml", key, default)


def _board_limit(board: str) -> float:
    """获取板块精确涨跌停限制（%）。

    涨跌停硬过滤必须用精确阈值（主板 10.0、创业板/科创板 20.0、北交所 30.0），
    而非预警宽松阈值（低 0.5%），否则会误排除 9.5%-9.99% 仍可交易的股票。
    """
    return board_exact_limit_pct(board)


def _min_survival_cap(board: str) -> float:
    """获取板块最低生存市值（亿），低于此视为退市风险。
    2026更新：注册制退市常态化，提高阈值。"""
    return _limit(
        f"min_survival_cap.{board}",
        {
            "主板": 5,
            "创业板": 3,
            "科创板": 3,
            "北交所": 2,
        }.get(board, 5),
    )


def _goodwill_threshold() -> float:
    return _limit("goodwill_ratio_warning", 30)


def _pledge_threshold() -> float:
    return _limit("pledge_ratio_warning", 70)


# P1-22: _st_prefixes() 已删除，ST 检测统一使用 data.pool.is_st


@dataclass
class AnalyzeContext:
    """_analyze_stock 的参数封装。"""

    code: str
    quote: dict
    fin_records: list
    strategy: str
    filters: dict
    kline_bars: list = None
    phase1: bool = False
    regime: str = "neutral"
    no_chip: bool = False


@dataclass
class ResultRowContext:
    """build_result_row 的参数封装。"""

    code: str
    quote_dict: dict
    fin: dict
    features: dict
    industry: str
    total: float
    parts: dict
    rejected: list


def compute_features(code: str, bars=None) -> dict:
    """计算技术指标特征（模块级函数，供 screener.py 等外部复用）。

    v2.4.1: 统一委托给 technical.pipeline.compute_indicators()，消除双份实现（T12）。

    Args:
        code: 股票代码（带 sh/sz 前缀）
        bars: 预取的 KlineBar 列表（可选，为 None 时自动获取）
    Returns:
        技术指标 dict：trend/ret20/ma10/ma20/volume_ratio/macd_signal/rsi/rsi_signal/vol_price_signal/closes
    """
    from technical.pipeline import compute_indicators

    if bars is None:
        from data import get_kline

        bars = get_kline(code, scale=240, datalen=240)

    result = compute_indicators(bars)

    # 补齐 compute_indicators 在数据不足时省略的字段，保持下游兼容
    result.setdefault("ma10", 0)
    result.setdefault("ma20", 0)
    result.setdefault("volume_ratio", 1.0)
    result.setdefault("rsi_signal", 0)

    return result


class ScreeningService:
    """选股服务。"""

    def __init__(self):
        self.default_strategy = "balanced"

    def screen(
        self,
        codes: List[str],
        strategy: str = "balanced",
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        选股筛选。

        Args:
            codes: 股票代码列表
            strategy: 策略名称
            filters: 筛选条件

        Returns:
            筛选结果列表
        """
        filters = filters or {}

        # 验证策略
        if strategy not in STRATEGIES:
            logger.warning(f"未知策略 {strategy}，使用默认策略")
            strategy = self.default_strategy

        # 标准化代码
        normalized_codes = []
        for c in codes:
            try:
                if validate_code(c):
                    normalized_codes.append(normalize_quote_code(c))
            except ValidationError:
                logger.warning(f"跳过无效代码: {c}")

        if not normalized_codes:
            return []

        # 获取行情数据
        quotes = get_quotes(normalized_codes)
        # quote.code 是纯数字（如 "600519"），normalized_codes 带 sh/sz 前缀
        # 用 normalize_quote_code 做反向映射，保证 lookup 命中
        quote_map = {normalize_quote_code(q.code): q for q in quotes}

        # 预获取财务数据和K线数据（并行）
        fin_cache = self._prefetch_finance(normalized_codes)
        kline_cache = self._prefetch_kline(normalized_codes)

        # 分析每只股票
        results = []
        for code in normalized_codes:
            quote = quote_map.get(code)
            if not quote:
                continue

            try:
                stock_result = self._analyze_stock(
                    AnalyzeContext(
                        code=code,
                        quote=quote,
                        fin_records=fin_cache.get(code, []),
                        strategy=strategy,
                        filters=filters,
                        kline_bars=kline_cache.get(code),
                    )
                )
                if stock_result:
                    results.append(stock_result)
            except Exception as e:
                logger.warning(f"分析失败 {code}: {e}")
                continue

        # 排序
        results.sort(key=lambda r: r.get("score", 0), reverse=True)

        return results

    def _prefetch_finance(self, codes: List[str]) -> Dict[str, List[dict]]:
        """预获取财务数据。"""
        from common import parallel_fetch_dict

        def fetch_one(code):
            try:
                records = get_finance(normalize_finance_code(code))
                return [r.to_dict() for r in records]
            except Exception as e:
                logger.warning("获取财务数据失败 %s: %s", code, e)
                return []

        return parallel_fetch_dict(codes, fetch_one, label="finance")

    def _prefetch_kline(
        self, codes: List[str], scale: int = 240, datalen: int = 240
    ) -> Dict[str, list]:
        """预获取K线数据（并行）。"""
        from common import parallel_fetch_dict

        def fetch_one(code):
            try:
                bars = get_kline(code, scale=scale, datalen=datalen)
                return bars
            except Exception as e:
                logger.warning("获取K线失败 %s: %s", code, e)
                return []

        return parallel_fetch_dict(codes, fetch_one, label="kline")

    def _analyze_stock(self, ctx: AnalyzeContext) -> Optional[Dict[str, Any]]:
        """分析单只股票。

        Args:
            ctx: 分析上下文（code, quote, fin_records, strategy, filters,
                 kline_bars, phase1, regime, no_chip）
        """
        quote_dict = ctx.quote.to_dict() if hasattr(ctx.quote, "to_dict") else ctx.quote
        fin = ctx.fin_records[0] if ctx.fin_records else {}

        # 行业分类
        industry = infer_industry(
            quote_dict.get("name", ""),
            ctx.code,
            fetcher_industry=quote_dict.get("industry", ""),
        )

        # 硬过滤
        rejected, filter_warnings = self._hard_filter(quote_dict, fin, ctx.filters)
        if rejected:
            return {
                "code": ctx.code,
                "name": quote_dict.get("name", ""),
                "score": 0,
                "rejected": rejected,
                "warnings": filter_warnings,
            }

        # 计算因子得分（P0-12: 传入策略权重，跳过权重为 0 的因子）
        features = self._compute_features(ctx.code, ctx.kline_bars)
        parts = compute_factor_parts(
            fin, quote_dict, features, industry, weights=get_strategy(ctx.strategy)
        )
        if ctx.no_chip:
            parts["chip"] = 50

        # 两阶段策略：Stage 1 硬条件过滤（review#2）
        if ctx.phase1 and STRATEGIES.get(ctx.strategy, {}).get("two_stage"):
            from strategies.filters.turning_point import turning_point_filter

            pass_, reason = turning_point_filter(quote_dict, fin, features)
            if not pass_:
                rejected = list(rejected) + [f"未通过拐点过滤: {reason}"]
                return build_result_row(
                    ResultRowContext(
                        code=ctx.code,
                        quote_dict=quote_dict,
                        fin=fin,
                        features=features,
                        industry=industry,
                        total=0,
                        parts=parts,
                        rejected=rejected,
                    )
                )

        total = compute_weighted_score(parts, ctx.strategy, regime=ctx.regime)
        return build_result_row(
            ResultRowContext(
                code=ctx.code,
                quote_dict=quote_dict,
                fin=fin,
                features=features,
                industry=industry,
                total=total,
                parts=parts,
                rejected=[],
            )
        )

    @staticmethod
    def _vol_price_signal_desc(signal: int) -> str:
        return "配合" if signal > 0 else "背离" if signal < 0 else "中性"

    @staticmethod
    def _compute_features(code: str, bars=None) -> dict:
        """计算技术指标特征（委托给模块级 compute_features）。"""
        return compute_features(code, bars=bars)

    def _hard_filter(self, quote: dict, fin: dict, filters: dict) -> tuple:
        """硬过滤。

        Args:
            quote: 行情 dict（含 total_cap/amount/change_pct/code/name）
            fin: 财务 dict（兼容标准化字段名与东财原始字段名）
            filters: 筛选条件 dict，支持：
                - min_amount (float, 万元): 最低成交额
                - min_cap (float, 亿): 最低市值
                - filter_loss (bool): 是否过滤亏损股（默认 True）
                - exclude_loss (bool): 附加排除 EPS<=0（需显式设置）
                - pledge_warning (bool): 质押率过高仅预警（默认 False）

        Returns:
            (reasons, warnings) 元组：reasons 非空表示硬拒绝，
            warnings 为软警告（不应导致拒绝）。P1-19: 分离避免 warning 误拒。
        """
        reasons = []
        warnings = []
        name = quote.get("name", "")
        code = quote.get("code", "")
        bd = board_type(code)
        eps = to_float(fin.get("eps", fin.get("EPSJB")))

        # 退市风险：市值过小（提高阈值，注册制后退市常态化）
        min_survival_cap = _min_survival_cap(bd)
        if 0 < to_float(quote.get("total_cap")) < min_survival_cap:
            reasons.append(f"市值<{min_survival_cap}亿(退市风险)")

        # ST 检测 + 财务类退市风险预警
        # 统一使用 data.pool.is_st（子串匹配，与 pool 层一致），
        # 避免 startswith(["ST","*ST"]) 漏判 S*ST 等变体。
        from data.pool import is_st

        is_st = is_st(name)
        if is_st:
            reasons.append("ST风险")
        else:
            # 财务类退市风险预警（2026新增）：营收<1亿+净利润为负+审计意见非标
            # P1-16: FinanceRecord 暂无营收绝对值字段（只有 revenue_yoy 同比%），
            # 原读 fin.get("revenue", TOTALOPERATEREVE) 永远为 0，预警永不触发，
            # 形成虚假安全感。改为基于 revenue_yoy 异常下滑的近似预警：
            # 营收同比大幅下滑（<-30%）+ 亏损，提示退市风险。
            revenue_yoy = to_float(
                fin.get("revenue_yoy", fin.get("TOTALOPERATEREVETZ", 0))
            )
            if eps < 0 and revenue_yoy < -30:
                warnings.append("营收大幅下滑+亏损(退市风险警示)")

        # 亏损过滤（改为可配置，默认过滤）
        filter_loss = filters.get("filter_loss", True)
        if filter_loss and eps < 0:
            reasons.append("EPS<0(亏损)")

        # 商誉减值风险（无数据时跳过）
        goodwill_ratio = to_float(
            fin.get("goodwill_ratio", fin.get("GOODWILL_RATIO", 0))
        )
        if goodwill_ratio > _goodwill_threshold():
            reasons.append(f"商誉/总资产>{goodwill_ratio:.0f}%(减值风险)")

        # 股权质押率过高（降为预警而非硬过滤，2026更新）
        pledge_ratio = to_float(fin.get("pledge_ratio", fin.get("PLEDGE_RATIO", 0)))
        pledge_as_warning = filters.get("pledge_warning", False)
        if pledge_ratio > _pledge_threshold():
            if pledge_as_warning:
                warnings.append(f"质押率>{pledge_ratio:.0f}%(偏高)")
            else:
                reasons.append(f"质押率>{pledge_ratio:.0f}%(爆仓风险)")

        # 板块差异化阈值
        base_min_amount = filters.get("min_amount", 5000)
        base_min_cap = filters.get("min_cap", 40)
        board_min_amount = {
            "主板": base_min_amount,
            "创业板": _limit("min_amount.创业板", int(base_min_amount * 0.7)),
            "科创板": _limit("min_amount.科创板", int(base_min_amount * 0.7)),
            "北交所": _limit("min_amount.北交所", int(base_min_amount * 1.5)),
        }
        board_min_cap = {
            "主板": base_min_cap,
            "创业板": _limit("min_total_cap.创业板", int(base_min_cap * 0.6)),
            "科创板": _limit("min_total_cap.科创板", int(base_min_cap * 0.6)),
            "北交所": _limit("min_total_cap.北交所", int(base_min_cap * 0.4)),
        }
        min_amt = board_min_amount.get(bd, base_min_amount)
        min_cap = board_min_cap.get(bd, base_min_cap)

        if to_float(quote.get("amount")) / 10000 < min_amt:
            label = f"成交额<{min_amt:.0f}万"
            if bd != "主板":
                label += f"({bd}阈值)"
            reasons.append(label)
        if to_float(quote.get("total_cap")) < min_cap:
            label = f"市值<{min_cap:.0f}亿"
            if bd != "主板":
                label += f"({bd}阈值)"
            reasons.append(label)

        # 涨跌停过滤：T+1 下当日无法交易（涨 ≥ 涨停 或 跌 ≤ -涨停）
        change_pct = to_float(quote.get("change_pct", 0))
        board_limit = _board_limit(bd)
        if change_pct >= board_limit or change_pct <= -board_limit:
            reasons.append("涨跌停限制")

        # 排除亏损（来自 filters）
        if filters.get("exclude_loss") and eps <= 0:
            reasons.append("EPS<=0")

        # P1-19: 返回 (reasons, warnings) 元组，warnings 不导致拒绝
        return reasons, warnings


def compute_factor_parts(fin, quote_dict, features, industry, weights=None):
    """计算所有因子得分（自动发现已注册因子）。

    Args:
        weights: 策略权重 dict。传入时权重为 0 的因子跳过计算（P0-12），
                 None 时全量计算（向后兼容）。
    """
    code = quote_dict.get("code", "")
    return compute_all_factors(fin, quote_dict, features, industry, code, weights)


# Sprint 9 两阶段管线（Sprint 末节架构建议）：
# Phase 1（轻量快速筛选）：仅算不依赖 K 线的因子
#   quality / valuation / liquidity / chip(static)
# Phase 2（精准评分）：在 Phase 1 Top N×3 上补 K 线依赖因子
#   momentum / volatility / dividend
PHASE1_FACTORS = ("quality", "valuation", "liquidity", "chip")
PHASE2_FACTORS = ("momentum", "volatility", "dividend")


def compute_phase1_parts(fin, quote_dict, industry: str, weights=None) -> dict:
    """Sprint 9 Phase 1：算 quality/valuation/liquidity/chip（不依赖 K 线）。

    适用于全市场 5000 只初筛，3-5 秒内完成。
    chip 使用静态评分（仅股东户数变化率，零网络开销）。

    Args:
        weights: 策略权重 dict。传入时权重为 0 的因子跳过计算（P0-12）。
    """
    code = quote_dict.get("code", "")
    parts = compute_phase_factors(1, fin, quote_dict, {}, industry, code, weights=weights)
    # Phase 1 chip 使用静态评分
    parts["chip"] = chip_score_static(code)
    return parts


def compute_phase2_parts(
    features: dict, quote_dict: dict, fin: dict, industry: str
) -> dict:
    """Sprint 9 Phase 2：算 momentum/volatility/dividend（依赖 K 线）。

    仅对 Phase 1 Top N×3 候选调用，节省 K 线获取量。
    chip 在 Phase 1 已用静态评分，Phase 2 不重复计算。
    """
    code = quote_dict.get("code", "")
    # P1-14: Phase 2 跳过 chip 因子（chip 注册为 phase=2 但 Phase 1 已用静态评分）。
    # 避免 compute_phase_factors 执行 chip_score_dynamic（3 次网络请求）后又被 pop 丢弃。
    parts = compute_phase_factors(
        2, fin, quote_dict, features, industry, code, exclude={"chip"}
    )
    return parts


def merge_phase_parts(phase1: dict, phase2: dict) -> dict:
    """合并 Phase 1 + Phase 2 因子分。"""
    return {**phase1, **phase2}


def compute_weighted_score(parts, strategy, regime=None):
    """按策略权重加权求和，支持 market regime overlay（Sprint 2）。

    Args:
        parts: 6 因子分 dict
        strategy: 策略名
        regime: 可选 RegimeState 枚举（bull/bear/range/panic）。
                None 时不应用 overlay。
    """
    weights = get_strategy(strategy)
    if regime is not None:
        from strategies.regime import compute_overlay_weights

        weights = compute_overlay_weights(weights, regime)

    # 检查 key 不匹配：parts 有但 weights 没有，或反之
    all_keys = (set(parts) | set(weights)) - {"label", "two_stage"}
    part_keys = set(parts) - {"label", "two_stage"}
    weight_keys = set(weights) - {"label", "two_stage"}
    missing_weights = part_keys - weight_keys
    missing_parts = weight_keys - part_keys
    if missing_weights or missing_parts:
        import logging
        logger = logging.getLogger(__name__)
        if missing_weights:
            logger.debug("compute_weighted_score: 因子 %s 有分数但无权重（策略 %s），按零贡献处理", missing_weights, strategy)
        if missing_parts:
            logger.debug("compute_weighted_score: 因子 %s 有权重但无分数（策略 %s），按中性50处理", missing_parts, strategy)

    # 缺失因子使用 50（中性值）而非 0，避免因数据缺失严重拉低综合评分
    return sum(
        parts.get(k, 50) * weights.get(k, 0)
        for k in all_keys
    )


def normalize_factors_batch(
    parts_list: List[Dict[str, float]],
) -> List[Dict[str, float]]:
    """对一批股票 6 因子做 cross-sectional z-score 标准化。

    每个因子的均值/方差从该批次计算，z = (x - mean) / std。
    输出范围约为 [-3, 3]，再线性映射到 [0, 100] 保留原有 [0,100] 评分语义。

    解决问题（review#14）：六因子评分范围差异巨大（quality 30-85, volatility 5-95），
    不加标准化导致 volatility 因子隐式权重超调。

    Args:
        parts_list: 候选股 7 因子 dict 列表

    Returns:
        标准化后的 7 因子 dict 列表（顺序与输入对应）
    """
    if not parts_list:
        return parts_list
    # 单股时无 cross-sectional 信息可计算，跳过归一化
    if len(parts_list) < 2:
        return [dict(p) for p in parts_list]
    import statistics

    keys = get_factor_keys()  # 从注册表自动获取，不再硬编码
    means = {k: statistics.mean(p.get(k, 0) for p in parts_list) for k in keys}
    stds = {k: (statistics.stdev(p.get(k, 0) for p in parts_list) or 1.0) for k in keys}
    out = []
    for p in parts_list:
        normed = dict(p)
        for k in keys:
            z = (p.get(k, 0) - means[k]) / stds[k]
            normed[k] = max(0.0, min(100.0, 50 + z * 15))  # z=0 → 50
        out.append(normed)
    return out


def compute_weighted_score_with_norm(
    parts_list: List[Dict[str, float]], strategy: str
) -> List[float]:
    """对批量 6 因子做归一化后加权求和。

    Args:
        parts_list: 候选股 6 因子 dict 列表
        strategy: 策略名

    Returns:
        每只股票的加权得分列表（与输入顺序对应）
    """
    if not parts_list:
        return []
    normed = normalize_factors_batch(parts_list)
    return [compute_weighted_score(p, strategy) for p in normed]


def build_result_row(ctx: ResultRowContext):
    """装配标准化结果 dict。"""
    code = ctx.code
    quote_dict = ctx.quote_dict
    fin = ctx.fin
    features = ctx.features
    industry = ctx.industry
    total = ctx.total
    parts = ctx.parts
    rejected = ctx.rejected
    bd = board_type(code)
    return {
        "code": code,
        "name": quote_dict.get("name", ""),
        "board": bd,
        "industry": industry,
        "score": round(total, 1),
        "quality": round(parts.get("quality", 0), 1),
        "valuation": round(parts.get("valuation", 0), 1),
        "momentum": round(parts.get("momentum", 0), 1),
        "liquidity": round(parts.get("liquidity", 0), 1),
        "volatility": round(parts.get("volatility", 0), 1),
        "dividend": round(parts.get("dividend", 0), 1),
        "chip": round(parts.get("chip", 50), 1),
        "price": quote_dict.get("price"),
        "change_pct": quote_dict.get("change_pct"),
        "pe": quote_dict.get("pe"),
        "pb": quote_dict.get("pb"),
        "roe": fin.get("roe", fin.get("ROEJQ", "-")),
        "profit_growth": fin.get("net_profit_yoy", fin.get("PARENTNETPROFITTZ", "-")),
        "ret20": round(features.get("ret20", 0), 1),
        "trend": (
            "上升"
            if features.get("trend", 0) > 0
            else "下降" if features.get("trend", 0) < 0 else "震荡"
        ),
        "rsi": features.get("rsi", 50),
        "macd_signal": features.get("macd_signal", 0),
        "vol_price": ScreeningService._vol_price_signal_desc(
            features.get("vol_price_signal", 0)
        ),
        "rejected": rejected,
    }


# ---------- re-export：保持原有公开 API 导入路径不变 ----------

# 数据 helpers（向后兼容：测试通过 ss.prefetch_* 访问）
from data.helpers import (  # noqa: E402, F401
    prefetch_finance_all,
    prefetch_kline_all,
    fetch_batch_dicts,
)

from business.universe_loader import (  # noqa: E402
    DATA_DIR,
    _BOARD_KEY_MAP,
    load_full_market_universe,
    load_universe,
    pre_screen_quotes,
    apply_portfolio_constraints,
)

from business.screening_pipeline import (  # noqa: E402
    analyze_code,
    analyze_code_phase1,
    run_screening,
)

__all__ = [
    "ScreeningService",
    "AnalyzeContext",
    "ResultRowContext",
    "DATA_DIR",
    "compute_features",
    "compute_factor_parts",
    "compute_weighted_score",
    "normalize_factors_batch",
    "compute_weighted_score_with_norm",
    "build_result_row",
    "analyze_code",
    "analyze_code_phase1",
    "load_universe",
    "load_full_market_universe",
    "pre_screen_quotes",
    "apply_portfolio_constraints",
    "run_screening",
]
