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
    _score_fundamentals,
    _score_valuation,
    _score_technical,
    _score_sentiment,
)

# 导入各专家评分函数
from . import buffett, lynch, soros, duan_yongping
from . import xu_xiang, zhao_laoge, chaogu_yangjia, zuoshou_xinyi

# v2.1.0 扩展视角：3 个合并 + 3 个补盲区
from . import value_anchor, topic_leader, emotion_tech
from . import sector_specialist, institution, risk_manager

# v2.2.0 新增：动量派（利弗莫尔+丹尼斯）
from . import momentum_trader

# v2.4.0 新增：价值机构锚（合并 value_anchor + institution）
from . import value_institution


def score_expert(
    profile: ExpertProfile,
    stock_data: dict,
) -> dict:
    """通用启发式评分（v1.3.2 fallback）。

    所有专家共用同一套简单规则，不区分专家风格。
    精确评分请使用 score_expert_precise()。

    .. deprecated:: v2.4.2
        P2-11 起 score_expert_precise 对未注册 profile 改回退到
        score_expert_precise_proxy（显式全 50 + warning），不再调用本函数。
        本函数保留供显式调用通用启发式，但不应作为 precise 的隐式回退。
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
        elif dim in ("情绪", "情绪/题材", "情绪/反身性", "情绪/资金", "sentiment"):
            dim_scores[dim] = _score_sentiment(market_features)
        elif dim in ("安全边际", "margin_of_safety", "margin"):
            margin = _score_valuation(quote, fin) * 0.5 + _score_fundamentals(fin) * 0.5
            dim_scores[dim] = round(margin, 1)
        elif dim in ("风险", "risk"):
            risk = (
                _score_fundamentals(fin) * 0.4
                + _score_valuation(quote, fin) * 0.3
                + (100 - float(fin.get("debt_ratio") or fin.get("ZCFZL") or 50)) * 0.3
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
    # ── legacy 8 人（active=False，保留为研究/A-B 对比档案）──
    # 注意：vote_engine.aggregate_votes 不会主动调用 legacy 评分；
    # 仅当用户显式 _EXPERT_SCORING_FUNCTIONS["buffett"](data) 时执行。
    "buffett": buffett.score,
    "duan_yongping": duan_yongping.score,
    "xu_xiang": xu_xiang.score,
    "zhao_laoge": zhao_laoge.score,
    "chaogu_yangjia": chaogu_yangjia.score,
    "zuoshou_xinyi": zuoshou_xinyi.score,
    "value_anchor": value_anchor.score,
    "institution": institution.score,
    # ── active 8 人（5 长线 + 3 短线）──
    "lynch": lynch.score,
    "soros": soros.score,
    "value_institution": value_institution.score,
    "sector_specialist": sector_specialist.score,
    "risk_manager": risk_manager.score,
    "topic_leader": topic_leader.score,
    "emotion_tech": emotion_tech.score,
    "momentum_trader": momentum_trader.score,
}


# 推理链注册表（v2.2.0，15 位专家全覆盖）
# 原仅 buffett 拥有 score_with_reasoning 接口，现统一用 generic_score_with_reasoning 包装
_EXPERT_SCORING_WITH_REASONING: Dict[str, Callable[[dict], Dict[str, object]]] = {
    "buffett": buffett.score_with_reasoning,
    "lynch": lynch.score_with_reasoning,
    "soros": soros.score_with_reasoning,
    "duan_yongping": duan_yongping.score_with_reasoning,
    "xu_xiang": xu_xiang.score_with_reasoning,
    "zhao_laoge": zhao_laoge.score_with_reasoning,
    "chaogu_yangjia": chaogu_yangjia.score_with_reasoning,
    "zuoshou_xinyi": zuoshou_xinyi.score_with_reasoning,
    "value_anchor": value_anchor.score_with_reasoning,
    "topic_leader": topic_leader.score_with_reasoning,
    "emotion_tech": emotion_tech.score_with_reasoning,
    "sector_specialist": sector_specialist.score_with_reasoning,
    "institution": institution.score_with_reasoning,
    "risk_manager": risk_manager.score_with_reasoning,
    # v2.2.0 新增：动量派
    "momentum_trader": momentum_trader.score_with_reasoning,
    # v2.4.0 新增：价值机构锚
    "value_institution": value_institution.score_with_reasoning,
}


def score_expert_with_reasoning(
    profile: ExpertProfile,
    stock_data: dict,
) -> dict:
    """调用对应专家的 score_with_reasoning，返回含推理链的评分结果。

    v2.2.0 新增：14 位专家全部支持 reasoning 输出，UX 一致。
    13 位新加专家通过 generic_score_with_reasoning 包装，仅 buffett 保留
    手写实现（其推理标签含具体阈值，UX 更精准）。
    """
    fn = _EXPERT_SCORING_WITH_REASONING.get(profile.name)
    if fn is None:
        from ._utils import generic_score_with_reasoning

        return generic_score_with_reasoning(
            profile, score_expert_precise_proxy, stock_data
        )
    return fn(stock_data)


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
        # P2-11: profile 未注册精确评分函数时，回退到 proxy（返回全 50 + warning），
        # 而非 score_expert 通用启发式。原因：通用启发式不区分专家风格，会产出
        # 误导性的"看似精确"评分；proxy 显式标注 fallback，让调用方知晓无精确逻辑。
        # 全 16 位 active/legacy 专家均已注册，此分支仅防御未知 profile。
        import logging

        logging.getLogger(__name__).warning(
            "score_expert_precise: %s 未注册精确评分函数，回退到 proxy（全 50 均分）",
            profile.name,
        )
        dim_scores = score_expert_precise_proxy(stock_data)
        # 补齐 profile.weights 中 proxy 未覆盖的维度（如"安全边际"）为 50
        for dim in profile.weights:
            dim_scores.setdefault(dim, 50.0)
        total = score_from_dimensions(profile, dim_scores)
        return {
            "score": round(total, 1),
            "direction": direction_from_score(total),
            "breakdown": dimension_breakdown(profile, dim_scores),
            "dim_scores": dim_scores,
            "method": "proxy_fallback",
        }

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


def consistency_from_scores(scores: List[float]) -> float:
    """从评分列表计算一致性分数（CV→一致性映射）。

    公式来源：decide.md §六.3。
    返回 0-100，越高表示专家意见越一致。
    """
    if not scores:
        return 0.0
    mean = statistics.mean(scores)
    if mean <= 0:
        return 0.0
    cv = statistics.stdev(scores) / mean if len(scores) > 1 else 0
    return max(0.0, min(100.0, 100 - cv * 150))


def score_expert_precise_proxy(stock_data: dict) -> Dict[str, float]:
    """fallback 评分代理：当 profile 未注册时返回均分 50。

    v2.2.0 score_expert_with_reasoning 的兜底路径使用。
    警告：此处无实际评分逻辑，仅作为 unknown profile 的安全回退。
    维度键从 profile.weights 动态获取，避免与专家特定维度名不匹配。
    """
    import logging

    _log = logging.getLogger(__name__)
    _log.warning(
        "score_expert_precise_proxy: fallback 路径触发，返回默认均分 50，传入数据键: %s",
        list(stock_data.keys()) if stock_data else "None",
    )
    # 标准五维度，兼容所有专家权重键名变体
    return {"基本面": 50.0, "估值": 50.0, "技术面": 50.0, "情绪": 50.0, "风险": 50.0}


def compute_confidence_index(
    expert_scores: List[float],
    composite_score: float,
    calibration_factor: float = 0.0,
) -> float:
    """计算信心指数（decide.md §六.3）。

    Args:
        expert_scores: 8 位 active 专家的评分列表
        composite_score: 调整后综合分
        calibration_factor: 校准因子，范围 [-1, 1]，默认 0（无校准数据）

    Returns:
        0-100 信心指数
    """
    if not expert_scores:
        return 50.0

    consistency = consistency_from_scores(expert_scores)
    # 校准因子贡献：calibration_factor ∈ [-1,1]，×10 后贡献 ±10 分（decide.md §6.3）。
    # 第六轮审查修正：原代码 cal_adjustment * 0.1 使实际贡献仅 ±1 分，与文档承诺的
    # ±10 分矛盾，且不足以让低准确率专家组（如短线 20%）实质压低信心。现改为直接
    # 贡献 ±10 分，与 decide.md §6.3 对齐。权重重新分配：一致性 0.40 + 综合分 0.40 +
    # 校准 0.20（其中校准的 0.20 上限 = 10 分，即 calibration_factor × 10）。
    cal_adjustment = calibration_factor * 10

    confidence = consistency * 0.40 + composite_score * 0.40 + cal_adjustment
    return max(0.0, min(100.0, round(confidence, 1)))


__all__ = [
    "score_from_dimensions",
    "dimension_breakdown",
    "score_expert",
    "score_expert_precise",
    "score_expert_with_reasoning",
    "compute_confidence_index",
    "consistency_from_scores",
]
