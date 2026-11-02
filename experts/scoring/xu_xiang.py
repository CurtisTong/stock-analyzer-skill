"""
徐翔专属评分函数。

维度：基本面(5%) + 估值(12%) + 技术面(30%) + 情绪/题材(43%) + 风险(10%)
精确复现 experts/xu_xiang.md §九 评分矩阵中的阈值规则。
"""

from typing import Dict

from ._utils import _safe_float


def score(stock_data: dict) -> Dict[str, float]:
    """徐翔专属评分：涨停基因 + 板块联动封单 + 流通市值。"""
    quote = stock_data.get("quote") or {}
    fin = stock_data.get("finance") or {}
    market = stock_data.get("market_features") or {}
    kline_data = stock_data.get("kline_data") or {}

    # 基本面：仅排雷
    eps = _safe_float(fin.get("EPSJB") or fin.get("eps"))
    base = 60 if eps > 0 else 0

    # 估值：流通市值
    # （v1.26.0）流通市值缺失时给中性 50，不当 0（最差）处理
    circ_cap_raw = quote.get("circulating_cap")
    if circ_cap_raw is None:
        val = 50
    else:
        circ_cap = _safe_float(circ_cap_raw)
        if 30 <= circ_cap <= 150:
            val = 100
        elif 150 < circ_cap <= 300:
            val = 60
        elif circ_cap > 500 or circ_cap < 30:
            val = 0
        else:
            val = 50

    # 技术面：涨停板基因
    # （v1.26.0）区分"0 次涨停"（数据可得且差）与"数据不可得"：
    # 原实现把缺失字段当 0 处理，直接给最差分 0，再被 weighted_merge 的
    # veto 阈值（<10 取最低分）放大成整维度归零——CLI 真实数据形态下
    # topic_leader 技术面被 veto 到 0.0（zhao_laoge 本会给 80）。
    # 数据不可得时给中性 50，不做隐性惩罚。
    limit_up_30d = market.get("limit_up_30d_count")
    if limit_up_30d is None or limit_up_30d == 0:
        # 从 K 线数据估算
        closes = kline_data.get("closes") or []
        if len(closes) >= 2:
            # 涨停阈值按板块区分（xu_xiang.md §决策逻辑）：
            # 主板 ±10%（用 0.095 容差），创业板/科创板 ±20%（用 0.195 容差）
            code = str(quote.get("code") or stock_data.get("code") or "")
            plain = code.lstrip("shSZ").lstrip("shsz")
            limit_threshold = 0.195 if plain.startswith(("300", "301", "688")) else 0.095
            limit_up_30d = sum(
                1
                for i in range(1, len(closes))
                if closes[i - 1] > 0 and (closes[i] / closes[i - 1] - 1) >= limit_threshold
            )
        elif limit_up_30d is None:
            # 字段缺失且无 K 线可估算 → 数据不可得，中性处理
            limit_up_30d = None
    if limit_up_30d is None:
        tech = 50
    elif limit_up_30d >= 2:
        tech = 100
    elif limit_up_30d >= 1:
        tech = 50
    else:
        tech = 0

    # 情绪/题材：板块联动 + 封单强度
    # （v1.26.0）字段可能为 None（上游无数据源时显式置 None），
    # 比较前必须归一化——直接比较会抛 TypeError 崩掉整个专家。
    sector_limits = market.get("sector_limit_up_count")
    sector_limits = _safe_float(sector_limits, 0) if sector_limits is not None else 0
    seal_ratio = market.get("seal_to_circ_ratio")
    seal_ratio = _safe_float(seal_ratio, 0) if seal_ratio is not None else 0
    if sector_limits >= 3 and seal_ratio > 0.01:
        sent = 100
    elif sector_limits >= 2:
        sent = 60
    elif sector_limits >= 1:
        sent = 20
    else:
        sent = 10

    # 风险：大盘趋势 + 炸板率 + 监管
    idx_above_ma20 = market.get("index_above_ma20")
    idx_above_ma20 = True if idx_above_ma20 is None else bool(idx_above_ma20)
    limit_up_total = _safe_float(market.get("limit_up_count"))
    if idx_above_ma20 and limit_up_total > 50:
        risk = 100
    elif not idx_above_ma20 or limit_up_total < 20:
        risk = 20
    else:
        risk = 60

    return {
        "基本面": base,
        "估值": val,
        "技术面": tech,
        "情绪/题材": sent,
        "风险": risk,
    }


def score_with_reasoning(stock_data: dict) -> Dict[str, object]:
    """徐翔评分（含推理链）。

    v2.2.0 起统一使用 generic_score_with_reasoning 模板。
    """
    from experts.registry import EXPERT_REGISTRY
    from ._utils import generic_score_with_reasoning

    profile = EXPERT_REGISTRY["xu_xiang"]
    return generic_score_with_reasoning(profile, score, stock_data)
