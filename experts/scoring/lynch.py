"""
彼得·林奇专属评分函数。

维度：基本面(35%) + 估值(28%) + 技术面(15%) + 情绪(10%) + 风险(12%)
精确复现 experts/lynch.md §九 评分矩阵中的阈值规则。
"""

from typing import Dict

from ._utils import _safe_float


def score(stock_data: dict) -> Dict[str, float]:
    """林奇专属评分：净利增速阶梯 + PEG 阶梯 + 负债率风险。"""
    quote = stock_data.get("quote") or {}
    fin = stock_data.get("finance") or {}
    kline = stock_data.get("kline_features") or {}

    # 基本面：净利增速阶梯
    profit_growth = _safe_float(
        fin.get("PARENTNETPROFITTZ") or fin.get("net_profit_yoy")
    )
    if profit_growth >= 25:
        base = 100
    elif profit_growth >= 20:
        base = 80
    elif profit_growth >= 15:
        base = 50
    else:
        base = 20

    # 估值：PEG 阶梯
    pe = _safe_float(quote.get("pe"))
    if pe > 0 and profit_growth > 0:
        peg = pe / profit_growth
        if peg <= 0.5:
            val = 100
        elif peg <= 1.0:
            val = 80
        elif peg <= 1.5:
            val = 50
        elif peg <= 2.0:
            val = 30
        else:
            val = 0
    else:
        val = 30

    # 技术面：趋势
    trend = kline.get("trend", 0)
    if trend > 0:
        tech = 80
    elif trend == 0:
        tech = 50
    else:
        tech = 20

    # 情绪：内部人交易 / 机构态度（梯度评分）
    market = stock_data.get("market_features") or {}
    insider = market.get("insider_net_buy")
    inst_holding = market.get("institutional_holding")
    sent = 50  # 默认中性
    if insider is not None and insider > 0:
        # 内部人净买入按金额分档
        if insider > 100000000:  # > 1亿
            sent = 100
        elif insider > 50000000:  # > 5000万
            sent = 85
        elif insider > 10000000:  # > 1000万
            sent = 70
        else:
            sent = 60
    elif inst_holding is not None:
        # 机构持仓比例梯度评分
        if inst_holding < 0.3:
            sent = 80  # 低持仓，加仓空间大
        elif inst_holding < 0.5:
            sent = 70
        elif inst_holding < 0.6:
            sent = 60
        elif inst_holding < 0.8:
            sent = 40
        else:
            sent = 20  # 高持仓，可能减仓

    # 风险：负债率
    debt = _safe_float(fin.get("ZCFZL") or fin.get("debt_ratio"))
    if debt < 60:
        risk = 100
    elif debt < 100:
        risk = 60
    else:
        risk = 0

    return {"基本面": base, "估值": val, "技术面": tech, "情绪": sent, "风险": risk}


def score_with_reasoning(stock_data: dict) -> Dict[str, object]:
    """林奇评分（含推理链）。

    v2.2.0 起统一使用 generic_score_with_reasoning 模板（v2.0.0 仅 buffett 有此接口）。
    """
    from experts.registry import EXPERT_REGISTRY
    from ._utils import generic_score_with_reasoning

    profile = EXPERT_REGISTRY["lynch"]
    return generic_score_with_reasoning(profile, score, stock_data)
