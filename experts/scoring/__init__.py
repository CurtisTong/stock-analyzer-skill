"""
专家评分引擎。

v1.3.2 引入通用启发式；v2.0.0 新增每位专家专属评分函数。

提供两套评分路径：
- score_expert(): 通用启发式（fallback，所有专家共用同一套简单规则）
- score_expert_precise(): 专家专属评分（精确复现 experts/*.md §九 评分矩阵）

通用路径供兼容和降级使用；精确路径是 debate 模式的推荐评分方式，
输出可作为 LLM 推理的量化基线参考。

Args:
    profile: ExpertProfile 实例
    dim_scores: Dict[dimension_name, 0..100]，缺维度视为 50 (中性)

Returns:
    0-100 之间的浮点分
"""
import statistics
from typing import Callable, Dict, List, Optional

from .. import ExpertProfile, direction_from_score

# 从子模块导入通用工具
from ._utils import (
    _safe_float,
    _get_clamp,
    _get_scoring_config,
    score_from_dimensions,
    dimension_breakdown,
)

# 导入各专家评分函数
from . import buffett, lynch, soros, duan_yongping
from . import xu_xiang, zhao_laoge, chaogu_yangjia, zuoshou_xinyi


# ═══════════════════════════════════════════════════════════════
# 通用启发式评分（v1.3.2，所有专家共用，作为 fallback）
# ═══════════════════════════════════════════════════════════════

def _score_fundamentals(fin: dict) -> float:
    """基本面维度：ROE + 净利增速 + 营收增速 + 毛利率。"""
    if not fin:
        return 50.0
    roe = float(fin.get("roe") or fin.get("ROEJQ") or 0)
    profit_yoy = float(fin.get("net_profit_yoy") or fin.get("PARENTNETPROFITTZ") or 0)
    revenue_yoy = float(fin.get("revenue_yoy") or fin.get("TOTALOPERATEREVETZ") or 0)
    gross_margin = float(fin.get("gross_margin") or fin.get("XSMLL") or 0)
    debt = float(fin.get("debt_ratio") or fin.get("ZCFZL") or 0)

    score = 0
    score += min(100, roe * 5)
    score += min(100, max(0, profit_yoy + 50))
    score += min(100, max(0, revenue_yoy + 50))
    score += min(100, gross_margin * 2)
    score += min(100, max(0, 100 - debt))
    return round(score / 5, 1)


def _score_valuation(quote: dict, fin: dict) -> float:
    """估值维度：PE + PEG。"""
    if not quote:
        return 50.0
    pe = float(quote.get("pe") or 0)
    pb = float(quote.get("pb") or 0)
    growth = float(fin.get("net_profit_yoy") or fin.get("PARENTNETPROFITTZ") or 0) if fin else 0

    if pe <= 0 and pb <= 0:
        return 50.0

    score = 0
    if pe > 0:
        if pe <= 15:
            score += 60
        elif pe <= 25:
            score += 45
        elif pe <= 40:
            score += 25
        else:
            score += 10
    if pb > 0 and pb <= 2:
        score += 20
    elif pb > 0 and pb <= 5:
        score += 10
    if pe > 0 and growth > 0:
        peg = pe / growth
        if peg <= 1.0:
            score += 20
        elif peg <= 2.0:
            score += 10
    return min(100, max(0, score))


def _score_technical(kline_features: dict) -> float:
    """技术面维度：趋势 + RSI + MACD。"""
    if not kline_features:
        return 50.0
    score = 50
    trend = kline_features.get("trend", 0)
    if trend > 0:
        score += 20
    elif trend < 0:
        score -= 20

    rsi = kline_features.get("rsi", 50)
    if 30 <= rsi <= 70:
        score += 5
    elif rsi > 80:
        score -= 15
    elif rsi < 20:
        score -= 5

    macd = kline_features.get("macd_signal", 0)
    if macd > 0:
        score += 10
    elif macd < 0:
        score -= 10

    return max(0, min(100, score))


def _score_sentiment(market_features: dict) -> float:
    """情绪/题材维度：基于市场行情（上涨家数比+涨停家数+炸板率+两融余额占比）。"""
    if not market_features:
        return 50.0
    score = 50

    advance_ratio = market_features.get("advance_ratio", None)
    if advance_ratio is not None:
        if advance_ratio > 0.6:
            score += 15
        elif advance_ratio > 0.4:
            score += 5
        elif advance_ratio < 0.3:
            score -= 15
        elif advance_ratio < 0.2:
            score -= 25

    nh_nl_ratio = market_features.get("nh_nl_ratio", None)
    if nh_nl_ratio is not None:
        if nh_nl_ratio > 1.5:
            score += 10
        elif nh_nl_ratio < 0.5:
            score -= 10
        elif nh_nl_ratio < 0.2:
            score -= 20

    limit_up_count = market_features.get("limit_up_count", 0)
    if limit_up_count > 80:
        score += 15
    elif limit_up_count > 50:
        score += 10
    elif limit_up_count > 30:
        score += 5
    elif limit_up_count < 15:
        score -= 15

    limit_down_count = market_features.get("limit_down_count", 0)
    if limit_down_count > 50:
        score -= 25
    elif limit_down_count > 20:
        score -= 10

    margin_ratio = market_features.get("margin_ratio", None)
    if margin_ratio is not None:
        if margin_ratio > 0.10:
            score -= 15
        elif margin_ratio < 0.04:
            score -= 5

    return max(0, min(100, score))


def score_expert(
    profile: ExpertProfile,
    stock_data: dict,
) -> dict:
    """通用启发式评分（v1.3.2 fallback）。

    所有专家共用同一套简单规则，不区分专家风格。
    精确评分请使用 score_expert_precise()。
    """
    quote = stock_data.get("quote") or {}
    fin = stock_data.get("finance") or {}
    kline_features = stock_data.get("kline_features") or {}
    market_features = stock_data.get("market_features") or {}

    dim_scores: Dict[str, float] = {}
    for dim in profile.weights:
        if dim in ("基本面", "fundamentals"):
            dim_scores[dim] = _score_fundamentals(fin)
        elif dim in ("估值", "valuation"):
            dim_scores[dim] = _score_valuation(quote, fin)
        elif dim in ("技术面", "technical"):
            dim_scores[dim] = _score_technical(kline_features)
        elif dim in ("情绪", "情绪/题材", "情绪/反身性", "sentiment"):
            dim_scores[dim] = _score_sentiment(market_features)
        elif dim in ("安全边际", "margin_of_safety", "margin"):
            margin = (_score_valuation(quote, fin) * 0.5 +
                      _score_fundamentals(fin) * 0.5)
            dim_scores[dim] = round(margin, 1)
        elif dim in ("风险", "risk"):
            risk = (
                _score_fundamentals(fin) * 0.4 +
                _score_valuation(quote, fin) * 0.3 +
                (100 - float(fin.get("debt_ratio") or fin.get("ZCFZL") or 50)) * 0.3
            )
            dim_scores[dim] = round(max(0, min(100, risk)), 1)
        else:
            dim_scores[dim] = 50.0

    total = score_from_dimensions(profile, dim_scores)
    return {
        "score": round(total, 1),
        "direction": direction_from_score(total),
        "breakdown": dimension_breakdown(profile, dim_scores),
        "dim_scores": dim_scores,
    }


# ═══════════════════════════════════════════════════════════════
# 专家评分函数注册表
# ═══════════════════════════════════════════════════════════════

_EXPERT_SCORING_FUNCTIONS: Dict[str, Callable[[dict], Dict[str, float]]] = {
    "buffett": buffett.score,
    "lynch": lynch.score,
    "soros": soros.score,
    "duan_yongping": duan_yongping.score,
    "xu_xiang": xu_xiang.score,
    "zhao_laoge": zhao_laoge.score,
    "chaogu_yangjia": chaogu_yangjia.score,
    "zuoshou_xinyi": zuoshou_xinyi.score,
}


def score_expert_precise(
    profile: ExpertProfile,
    stock_data: dict,
) -> dict:
    """专家专属评分（v2.0.0）。

    精确复现 experts/*.md §九 评分矩阵中的阈值规则，
    每位专家有独立的评分函数。输出可作为 debate 模式的量化基线参考。

    Args:
        profile: 专家人设
        stock_data: 股票数据，支持以下字段：
            - quote: 行情 dict
                - pe: 市盈率（倍）
                - pb: 市净率（倍）
                - circulating_cap: 流通市值（**亿元**），各专家阈值基于此单位
                - price: 当前股价（元）
                - pe_percentile: PE 近5年历史分位（0-100）
            - finance: 财务 dict
                - ROEJQ/roe: ROE（%）
                - PARENTNETPROFITTZ/net_profit_yoy: 净利润同比增速（%）
                - ZCFZL/debt_ratio: 资产负债率（%）
                - EPSJB/eps: 每股收益（元）
                - MGJYXJJE/ocf_per_share: 每股经营现金流（元）
            - kline_features: 技术指标 dict（trend/rsi/macd_signal）
            - kline_data: K线原始数据 dict
                - closes: 收盘价列表（按时间正序）
                - volumes: 成交量列表
            - market_features: 市场特征 dict
                - limit_up_count/limit_down_count: 涨停/跌停家数
                - advance_ratio: 上涨家数比（0-1）
                - break_rate: 炸板率（0-1）
                - limit_up_30d_count: 近30日涨停次数
                - sector_limit_up_count: 同板块涨停家数

    Returns:
        {
            "score": 0-100 总分,
            "direction": 方向标签,
            "breakdown": {dim: weighted_contribution, ...},
            "dim_scores": {dim: raw_0_100, ...},
            "method": "precise",
        }
    """
    scoring_fn = _EXPERT_SCORING_FUNCTIONS.get(profile.name)
    if scoring_fn is None:
        # 回退到通用启发式
        result = score_expert(profile, stock_data)
        result["method"] = "fallback"
        return result

    dim_scores = scoring_fn(stock_data)

    # 确保所有权重维度都有评分
    for dim in profile.weights:
        if dim not in dim_scores:
            dim_scores[dim] = 50.0

    total = score_from_dimensions(profile, dim_scores)
    return {
        "score": round(total, 1),
        "direction": direction_from_score(total),
        "breakdown": dimension_breakdown(profile, dim_scores),
        "dim_scores": dim_scores,
        "method": "precise",
    }


# ═══════════════════════════════════════════════════════════════
# 信心指数计算（含校准因子）
# ═══════════════════════════════════════════════════════════════

def compute_confidence_index(
    expert_scores: List[float],
    composite_score: float,
    calibration_factor: float = 0.0,
) -> float:
    """计算信心指数（decide.md §六.3）。

    Args:
        expert_scores: 8 位专家的评分列表
        composite_score: 调整后综合分
        calibration_factor: 校准因子，范围 [-1, 1]，默认 0（无校准数据）

    Returns:
        0-100 信心指数
    """
    if not expert_scores:
        return 50.0

    mean = statistics.mean(expert_scores)
    if mean > 0:
        cv = statistics.stdev(expert_scores) / mean if len(expert_scores) > 1 else 0
    else:
        cv = 1.0

    consistency = max(0.0, min(100.0, 100 - cv * 150))
    cal_adjustment = calibration_factor * 10  # 归一化后 ×10，校准贡献不超过 ±10 分

    confidence = consistency * 0.35 + composite_score * 0.55 + cal_adjustment * 0.1
    return max(0.0, min(100.0, round(confidence, 1)))


# ═══════════════════════════════════════════════════════════════
# 向后兼容：暴露内部函数供测试直接导入
# ═══════════════════════════════════════════════════════════════

_score_buffett = buffett.score
_score_lynch = lynch.score
_score_soros = soros.score
_score_duan_yongping = duan_yongping.score
_score_xu_xiang = xu_xiang.score
_score_zhao_laoge = zhao_laoge.score
_score_chaogu_yangjia = chaogu_yangjia.score
_score_zuoshou_xinyi = zuoshou_xinyi.score


__all__ = [
    "score_from_dimensions",
    "dimension_breakdown",
    "score_expert",
    "score_expert_precise",
    "compute_confidence_index",
    # 向后兼容
    "_score_buffett",
    "_score_lynch",
    "_score_soros",
    "_score_duan_yongping",
    "_score_xu_xiang",
    "_score_zhao_laoge",
    "_score_chaogu_yangjia",
    "_score_zuoshou_xinyi",
]
