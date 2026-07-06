"""
炒股养家专属评分函数。

维度：基本面(5%) + 估值(12%) + 技术面(15%) + 情绪(58%) + 风险(10%)
精确复现 experts/chaogu_yangjia.md §九 评分矩阵中的阈值规则。
"""

from typing import Dict

from ._utils import _safe_float


def score(stock_data: dict) -> Dict[str, float]:
    """养家专属评分：情绪周期阶段（冰点/主升/震荡/退潮）为绝对核心。"""
    quote = stock_data.get("quote") or {}
    market = stock_data.get("market_features") or {}

    # 基本面：仅题材
    base = 50

    # 估值：流通市值
    circ_cap = _safe_float(quote.get("circulating_cap"))
    val = 100 if 0 < circ_cap < 200 else 50

    # 技术面：市场温度计
    limit_up = market.get("limit_up_count", 0)
    if limit_up > 80:
        tech = 100
    elif limit_up >= 40:
        tech = 50
    else:
        tech = 0

    # 情绪：情绪周期阶段（核心维度）
    limit_down = market.get("limit_down_count", 0)
    break_rate = market.get("break_rate", 0)
    if limit_down > 50 and break_rate > 0.6:
        sent = 100  # 冰点转折
    elif limit_up > 80 and break_rate < 0.2:
        sent = 80  # 主升初期
    elif 40 <= limit_up <= 60:
        sent = 50  # 震荡
    elif limit_up < 20 or limit_down > 30:
        sent = 0  # 退潮
    else:
        sent = 40

    # 风险：跌停家数
    if limit_down < 10:
        risk = 100
    elif limit_down <= 30:
        risk = 30
    else:
        risk = 0

    return {"基本面": base, "估值": val, "技术面": tech, "情绪": sent, "风险": risk}


def score_with_reasoning(stock_data: dict) -> Dict[str, object]:
    """炒股养家评分（含推理链）。

    v2.2.0 起统一使用 generic_score_with_reasoning 模板。
    """
    from experts.registry import EXPERT_REGISTRY
    from ._utils import generic_score_with_reasoning

    profile = EXPERT_REGISTRY["chaogu_yangjia"]
    return generic_score_with_reasoning(profile, score, stock_data)
