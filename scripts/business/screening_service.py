"""
选股服务 (Business 层)。

提供选股筛选的业务逻辑，与 CLI 层解耦。
"""

import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from common import (
    DATA_DIR,
    board_type,
    board_exact_limit_pct,
    clamp,
    get_shared_executor,
    normalize_finance_code,
    normalize_quote_code,
    plain_code,
    to_float,
)
from common.exceptions import ValidationError
from common.validators import validate_code
from data import get_quotes, get_kline, get_finance
from data.helpers import (
    fetch_quote_dict,
    fetch_batch_dicts,
    fetch_kline_dicts,
    fetch_finance_dicts,
    fetch_finance_first,
    prefetch_finance_all,
    prefetch_kline_all,
)
from classifier import infer_industry
from strategies import (
    STRATEGIES,
    chip_score_static,
    get_strategy,
)
from strategies.filters import PRE_SCREEN_FILTER as _PRE_SCREEN
from strategies.factors.registry import (
    compute_all_factors,
    compute_phase_factors,
    get_factor_keys,
)

logger = logging.getLogger(__name__)

# board_type() 返回值 → all_stocks.json 中的键名映射
# board_type() 返回 "主板"，但 all_stocks.json 按上市板块分为 "主板沪" 和 "主板深"
_BOARD_KEY_MAP = {
    "主板": ["主板沪", "主板深"],
    "创业板": ["创业板"],
    "科创板": ["科创板"],
    "北交所": ["北交所"],
}


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
    rsi_data = rsi_features(closes) or {}
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
        phase1: bool = False,
        regime=None,
        no_chip: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """分析单只股票。

        Args:
            phase1: True 时执行两阶段拐点过滤（仅 two_stage 策略生效）。
                    对应原 screener.analyze_code 中的两阶段逻辑。
            regime: 可选市场状态枚举，传入时加权应用 overlay。
            no_chip: True 时 chip 因子给中性分 50。
        """
        quote_dict = quote.to_dict() if hasattr(quote, "to_dict") else quote
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
        if no_chip:
            parts["chip"] = 50

        # 两阶段策略：Stage 1 硬条件过滤（review#2）
        if phase1 and STRATEGIES.get(strategy, {}).get("two_stage"):
            from strategies.filters.turning_point import turning_point_filter

            pass_, reason = turning_point_filter(quote_dict, fin, features)
            if not pass_:
                rejected = list(rejected) + [f"未通过拐点过滤: {reason}"]
                return build_result_row(
                    code, quote_dict, fin, features, industry, 0, parts, rejected
                )

        total = compute_weighted_score(parts, strategy, regime=regime)
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
            # P1-16: FinanceRecord 暂无营收绝对值字段（只有 revenue_yoy 同比%），
            # 原读 fin.get("revenue", TOTALOPERATEREVE) 永远为 0，预警永不触发，
            # 形成虚假安全感。改为基于 revenue_yoy 异常下滑的近似预警：
            # 营收同比大幅下滑（<-30%）+ 亏损，提示退市风险。
            revenue_yoy = to_float(fin.get("revenue_yoy", fin.get("TOTALOPERATEREVETZ", 0)))
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


# ---------- 模块级 analyze 入口（替代原 screener.py 镜像重复） ----------


def analyze_code(
    quote,
    strategy,
    args,
    finance_cache=None,
    regime=None,
    kline_cache=None,
):
    """分析单只股票（CLI 友好入口，接受 quote dict）。

    合并自原 screener.analyze_code，两阶段拐点过滤在 two_stage 策略时生效。
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
        features = compute_features(quote_code, bars=kline_cache[quote_code])
    else:
        features = compute_features(quote_code)

    filters = {
        "min_amount": args.min_amount,
        "min_cap": args.min_cap,
        "exclude_loss": args.exclude_loss,
    }
    rejected = ScreeningService()._hard_filter(quote, fin, filters)

    industry = infer_industry(
        quote.get("name", ""), quote_code, fetcher_industry=quote.get("industry", "")
    )
    parts = compute_factor_parts(fin, quote, features, industry)
    if getattr(args, "no_chip", False):
        parts["chip"] = 50

    # 两阶段策略：Stage 1 硬条件过滤（review#2）
    if STRATEGIES.get(strategy, {}).get("two_stage"):
        from strategies.filters.turning_point import turning_point_filter

        pass_, reason = turning_point_filter(quote, fin, features)
        if not pass_:
            rejected = list(rejected) + [f"未通过拐点过滤: {reason}"]
            return build_result_row(
                quote_code, quote, fin, features, industry, 0, parts, rejected
            )

    total = compute_weighted_score(parts, strategy, regime=regime)
    return build_result_row(quote_code, quote, fin, features, industry, total, parts, rejected)


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
    svc = ScreeningService()
    rejected = svc._hard_filter(quote, fin, filters)
    industry = infer_industry(
        quote.get("name", ""), quote_code, fetcher_industry=quote.get("industry", "")
    )
    parts = compute_phase1_parts(fin, quote, industry)
    if getattr(args, "no_chip", False):
        parts["chip"] = 50
    total = compute_weighted_score(parts, args.strategy, regime=regime)
    return build_result_row(
        quote_code,
        quote,
        fin,
        {"ret20": 0, "rsi": 50, "macd_signal": 0, "vol_price_signal": 0, "trend": 0},
        industry,
        total,
        parts,
        rejected,
    )


def _apply_factor_normalization(rows, strategy, regime=None):
    """对所有候选股的 6 因子做 z-score 标准化并重新计算 score。"""
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


# ---------- 纯业务逻辑（从 screener.py 下沉） ----------


def load_full_market_universe(boards=None):
    """从 data/all_stocks.json 加载全市场股票池。"""
    path = DATA_DIR / "all_stocks.json"
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
    mapping_path = DATA_DIR / "sector_mapping.json"
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
    path = DATA_DIR / "sector_stocks.json"
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
    """全市场模式预筛选：排除 ST / 停牌 / 低流动性 / 低市值股票。"""
    before = len(quotes)
    result = []
    for q in quotes:
        name = q.get("name", "")
        if "ST" in name.upper():
            continue
        amount_yuan = to_float(q.get("amount", 0))
        if amount_yuan <= 0:
            continue
        bt = board_type(q.get("code", ""))
        if bt == "其他":
            continue
        min_amt = _PRE_SCREEN["min_amount"].get(bt, 5000) * 10000
        if amount_yuan < min_amt:
            continue
        cap = to_float(q.get("total_cap", 0))
        min_cap = _PRE_SCREEN["min_cap"].get(bt, 40)
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
    print(f"全市场预筛选: {before} → {after} 只（排除 ST/停牌/低流动性/低市值）")
    return result


def apply_portfolio_constraints(
    rows: list, sector_cap: float = 0.30, trend_penalty: float = 0.70
) -> list:
    """应用组合层面约束。"""
    if not rows:
        return rows

    min_pool_for_sector_cap = 10
    if len(rows) >= min_pool_for_sector_cap:
        max_per_sector = max(2, int(len(rows) * sector_cap))
    else:
        max_per_sector = len(rows)

    sector_count = {}
    result = []
    for stock in rows:
        industry = stock.get("industry", "默认")
        if sector_count.get(industry, 0) >= max_per_sector:
            continue
        if stock.get("trend") == "下降":
            stock["score"] = round(stock["score"] * trend_penalty, 1)
        sector_count[industry] = sector_count.get(industry, 0) + 1
        result.append(stock)

    result.sort(key=lambda r: r["score"], reverse=True)
    return result


# ---------- run_screening 编排（progress_callback 模式） ----------


def run_screening(args, progress_callback: Optional[Callable] = None) -> dict:
    """选股管线编排（业务层，与 CLI 输出解耦）。

    Args:
        args: CLI Namespace
        progress_callback: 可选回调，签名 callback(event: str, payload: dict) -> None。
            事件类型：market_regime / macro / phase1_done / phase2_done /
            single_done / pre_screen / snapshot / empty_universe

    Returns:
        dict: {rows, regime, macro_state, phase_stats, snapshot_path, halted}
    """
    import time as _time

    def _cb(event, payload=None):
        if progress_callback:
            progress_callback(event, payload or {})

    codes = load_universe(args)
    if not codes:
        _cb("empty_universe")
        return {"rows": [], "regime": None, "macro_state": None,
                "phase_stats": {}, "snapshot_path": None, "halted": True}

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
            _cb("market_regime", {"regime": regime})
        except Exception as e:
            print(f"⚠️ 市场状态检测失败: {e}", file=sys.stderr)
            regime = None

    # 宏观安全垫检查
    macro_state = None
    halted = False
    if not getattr(args, "no_macro", False):
        try:
            from strategies.macro import MacroSafetyGate

            gate = MacroSafetyGate()
            macro_state, macro_msg = gate.check()
            _cb("macro", {"msg": macro_msg, "state": macro_state})
            if macro_state.value == "RED":
                _cb("macro_red")
                halted = True
                return {"rows": [], "regime": regime, "macro_state": macro_state,
                        "phase_stats": phase_stats, "snapshot_path": None,
                        "halted": True}
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
        rows_p1.sort(key=lambda r: r.get("score", 0), reverse=True)
        top_n_phase2 = max(args.top * 3, 10)
        top_quotes = [q for q, r in zip(quotes, rows_p1) if r.get("score", 0) > 0][
            :top_n_phase2
        ]
        t_p1 = _time.perf_counter() - t_p1
        _cb("phase1_done", {"count_in": len(quotes), "count_out": len(top_quotes),
                            "elapsed": t_p1})

        t_p2 = _time.perf_counter()
        kline_cache = prefetch_kline_all([q["code"] for q in top_quotes])
        rows = [
            analyze_code(q, args.strategy, args, finance_cache,
                         regime=regime, kline_cache=kline_cache)
            for q in top_quotes
        ]
        if not args.no_normalize and len(rows) >= 3:
            _apply_factor_normalization(rows, args.strategy, regime=regime)
        t_p2 = _time.perf_counter() - t_p2
        t_total = _time.perf_counter() - t_pipeline_start
        phase_stats = {"p1_elapsed": t_p1, "p2_elapsed": t_p2, "total": t_total,
                       "saved_kline": len(quotes) - len(top_quotes)}
        _cb("phase2_done", {"count": len(rows), "elapsed": t_p2, "total": t_total,
                            "saved_kline": len(quotes) - len(top_quotes)})
    else:
        kline_cache = prefetch_kline_all([q["code"] for q in quotes])
        rows = [
            analyze_code(q, args.strategy, args, finance_cache,
                         regime=regime, kline_cache=kline_cache)
            for q in quotes
        ]
        if not args.no_normalize and len(rows) >= 3:
            _apply_factor_normalization(rows, args.strategy, regime=regime)
        _cb("single_done", {"count": len(rows)})

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

    return {"rows": rows, "regime": regime, "macro_state": macro_state,
            "phase_stats": phase_stats, "snapshot_path": snapshot_path,
            "halted": False}


__all__ = [
    "ScreeningService",
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
