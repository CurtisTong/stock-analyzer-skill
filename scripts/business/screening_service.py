"""
选股服务 (Business 层)。

提供选股筛选的业务逻辑，与 CLI 层解耦。
"""

import logging
from typing import List, Dict, Any, Optional

from common import to_float, normalize_quote_code, board_type, get_shared_executor
from common.exceptions import ValidationError
from common.validators import validate_code
from data import get_quote, get_quotes, get_kline, get_finance
from classifier import infer_industry
from strategies import (
    STRATEGIES,
    quality_score,
    valuation_score,
    momentum_score,
    liquidity_score,
    volatility_from_closes,
    dividend_score,
    chip_score_static,
    chip_score_dynamic,
)
from strategies.thresholds import get_industry_threshold
from strategies.factors.registry import (
    compute_all_factors,
    compute_phase_factors,
    get_factor_keys,
)

logger = logging.getLogger(__name__)


def _limit(key: str, default):
    """读取 limits.yaml 中的阈值；无 config 时回退到硬编码默认。"""
    from config.loader import safe_get

    return safe_get("limits.yaml", key, default)


def _board_limit(board: str) -> float:
    """获取板块涨跌停限制（%）。"""
    return _limit(
        f"board_limits.{board}",
        {
            "主板": 9.5,
            "创业板": 19.5,
            "科创板": 19.5,
            "北交所": 29.5,
        }.get(board, 9.5),
    )


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


def _st_prefixes() -> list:
    return _limit("st_prefixes", ["ST", "*ST"])


def compute_features(code: str, bars=None) -> dict:
    """计算技术指标特征（模块级函数，供 screener.py 等外部复用）。

    Args:
        code: 股票代码（带 sh/sz 前缀）
        bars: 预取的 KlineBar 列表（可选，为 None 时自动获取）
    Returns:
        技术指标 dict：trend/ret20/ma10/ma20/volume_ratio/macd_signal/rsi/rsi_signal/vol_price_signal/closes
    """
    import statistics
    from technical import macd_full, rsi_features
    from technical.volume import volume_analysis as _vol_analysis

    if bars is None:
        from data import get_kline

        bars = get_kline(code, scale=240, datalen=240)
    # 统一过滤：整条记录 close 和 volume 都 > 0 才保留，确保数组对齐
    valid_bars = [b for b in bars if b.close > 0 and b.volume > 0]
    closes = [b.close for b in valid_bars]
    volumes = [b.volume for b in valid_bars]

    if len(closes) < 10:
        # K 线数据不足时返回中性特征，避免下游因子函数 KeyError
        return {
            "trend": 0,
            "ret20": 0,
            "ma10": 0,
            "ma20": 0,
            "volume_ratio": 1.0,
            "rsi": 50,
            "rsi_signal": 0,
            "macd_signal": 0,
            "vol_price_signal": 0,
            "closes": [],
        }

    # 趋势
    ma10 = statistics.mean(closes[-10:])
    ma20 = (
        statistics.mean(closes[-20:]) if len(closes) >= 20 else statistics.mean(closes)
    )
    trend = 1 if closes[-1] > ma10 > ma20 else (-1 if closes[-1] < ma10 < ma20 else 0)

    # 20日收益率
    base = closes[-21] if len(closes) >= 21 else closes[0]
    ret20 = (closes[-1] / base - 1) * 100 if base else 0

    # 量比
    recent_vol = statistics.mean(volumes[-5:]) if len(volumes) >= 5 else 0
    base_vol = statistics.mean(volumes[-20:-5]) if len(volumes) >= 20 else recent_vol
    volume_ratio = recent_vol / base_vol if base_vol else 1

    # RSI
    rsi_data = rsi_features(closes)
    rsi = rsi_data.get("rsi", 50)
    rsi_signal = rsi_data.get("signal", 0)

    # MACD
    macd = macd_full(closes) or {}
    macd_signal = macd.get("signal", 0)

    # 量价关系（v1.3.2：复用 technical.volume.volume_analysis）
    vp = _vol_analysis(closes, volumes) or {}
    vol_price_signal = vp.get("volume_price_signal", 0)

    return {
        "trend": trend,
        "ret20": ret20,
        "ma10": ma10,
        "ma20": ma20,
        "volume_ratio": volume_ratio,
        "macd_signal": macd_signal,
        "rsi": round(rsi, 1),
        "rsi_signal": rsi_signal,
        "vol_price_signal": vol_price_signal,
        "closes": closes,
    }


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
                    code,
                    quote,
                    fin_cache.get(code, []),
                    strategy,
                    filters,
                    kline_cache.get(code),
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
        from data import get_finance
        from common import normalize_finance_code, parallel_fetch_dict

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
        from data import get_kline
        from common import parallel_fetch_dict

        def fetch_one(code):
            try:
                bars = get_kline(code, scale=scale, datalen=datalen)
                return bars
            except Exception as e:
                logger.warning("获取K线失败 %s: %s", code, e)
                return []

        return parallel_fetch_dict(codes, fetch_one, label="kline")

    def _analyze_stock(
        self,
        code: str,
        quote,
        fin_records: List[dict],
        strategy: str,
        filters: Dict[str, Any],
        kline_bars: list = None,
    ) -> Optional[Dict[str, Any]]:
        """分析单只股票。"""
        quote_dict = quote.to_dict()
        fin = fin_records[0] if fin_records else {}

        # 行业分类
        industry = infer_industry(
            quote_dict.get("name", ""),
            code,
            fetcher_industry=quote_dict.get("industry", ""),
        )

        # 硬过滤
        rejected = self._hard_filter(quote_dict, fin, filters)
        if rejected:
            return {
                "code": code,
                "name": quote_dict.get("name", ""),
                "score": 0,
                "rejected": rejected,
            }

        # 计算因子得分
        features = self._compute_features(code, kline_bars)
        parts = compute_factor_parts(fin, quote_dict, features, industry)
        total = compute_weighted_score(parts, strategy)
        return build_result_row(
            code, quote_dict, fin, features, industry, total, parts, []
        )

    @staticmethod
    def _vol_price_signal_desc(signal: int) -> str:
        return "配合" if signal > 0 else "背离" if signal < 0 else "中性"

    @staticmethod
    def _compute_features(code: str, bars=None) -> dict:
        """计算技术指标特征（委托给模块级 compute_features）。"""
        return compute_features(code, bars=bars)

    def _hard_filter(self, quote: dict, fin: dict, filters: dict) -> List[str]:
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
        upper_name = name.upper()
        is_st = any(upper_name.startswith(p) for p in _st_prefixes())
        if is_st:
            reasons.append("ST风险")
        else:
            # 财务类退市风险预警（2026新增）：营收<1亿+净利润为负+审计意见非标
            revenue = to_float(fin.get("revenue", fin.get("TOTALOPERATEREVE", 0)))
            revenue_billion = revenue / 100000000  # 转为亿元
            if eps < 0 and 0 < revenue_billion < 1:
                warnings.append("营收<1亿+亏损(退市风险警示)")

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

        # 附加警告信息（不影响筛选结果）
        if warnings:
            reasons.append(";".join(warnings[:2]))
        return reasons


def compute_factor_parts(fin, quote_dict, features, industry):
    """计算所有因子得分（自动发现已注册因子）。"""
    code = quote_dict.get("code", "")
    return compute_all_factors(fin, quote_dict, features, industry, code)


# Sprint 9 两阶段管线（Sprint 末节架构建议）：
# Phase 1（轻量快速筛选）：仅算不依赖 K 线的因子
#   quality / valuation / liquidity / chip(static)
# Phase 2（精准评分）：在 Phase 1 Top N×3 上补 K 线依赖因子
#   momentum / volatility / dividend
PHASE1_FACTORS = ("quality", "valuation", "liquidity", "chip")
PHASE2_FACTORS = ("momentum", "volatility", "dividend")


def compute_phase1_parts(fin, quote_dict, industry: str) -> dict:
    """Sprint 9 Phase 1：算 quality/valuation/liquidity/chip（不依赖 K 线）。

    适用于全市场 5000 只初筛，3-5 秒内完成。
    chip 使用静态评分（仅股东户数变化率，零网络开销）。
    """
    code = quote_dict.get("code", "")
    parts = compute_phase_factors(1, fin, quote_dict, {}, industry, code)
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
    parts = compute_phase_factors(2, fin, quote_dict, features, industry, code)
    # chip 已在 Phase 1 用静态评分，移除 Phase 2 的动态评分
    parts.pop("chip", None)
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
    weights = STRATEGIES[strategy]
    if regime is not None:
        from strategies.regime import compute_overlay_weights

        weights = compute_overlay_weights(weights, regime)
    return sum(
        parts.get(k, 0) * weights.get(k, 0)
        for k in set(parts) | set(weights)
        if k not in ("label", "two_stage")
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


def build_result_row(code, quote_dict, fin, features, industry, total, parts, rejected):
    """装配标准化结果 dict。"""
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


__all__ = [
    "ScreeningService",
    "compute_features",
    "compute_factor_parts",
    "compute_weighted_score",
    "normalize_factors_batch",
    "compute_weighted_score_with_norm",
    "build_result_row",
]
