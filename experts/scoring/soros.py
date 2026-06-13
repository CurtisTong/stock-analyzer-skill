"""
索罗斯专属评分函数。

维度：基本面(15%) + 估值(10%) + 技术面(25%) + 情绪/反身性(30%) + 风险(20%)
精确复现 experts/soros.md §九 评分矩阵中的阈值规则。
"""
from typing import Dict

from ._utils import _safe_float, _get_scoring_config


# 索罗斯流动性阈值默认值（向后兼容）
_SOROS_LIQUIDITY_FLOOR_DEFAULT = 5000


def score(stock_data: dict) -> Dict[str, float]:
    """索罗斯专属评分：趋势强度 + 反身性（逆向情绪）+ 流动性风险。"""
    quote = stock_data.get("quote") or {}
    fin = stock_data.get("finance") or {}
    kline = stock_data.get("kline_features") or {}
    market = stock_data.get("market_features") or {}

    # 基本面：仅作背景
    roe = _safe_float(fin.get("ROEJQ") or fin.get("roe"))
    profit_growth = _safe_float(fin.get("PARENTNETPROFITTZ") or fin.get("net_profit_yoy"))
    base = 60 if roe >= 15 else 30
    if profit_growth > 20:
        base = max(base, 60)

    # 估值：PE 分位
    pe = _safe_float(quote.get("pe"))
    if pe > 0 and pe < 25:
        val = 80
    elif pe > 60:
        val = 0
    else:
        val = 50

    # 技术面：趋势强度 + 量能
    kline_data = stock_data.get("kline_data") or {}
    closes = kline_data.get("closes") or []
    volumes = kline_data.get("volumes") or []
    if len(closes) >= 10:
        recent = closes[-10:]
        up_count = sum(1 for i in range(len(recent) - 1) if recent[i] < recent[i + 1])
        if up_count >= 9:
            tech = 100
        elif up_count <= 1:
            tech = 0
        else:
            tech = 40
    else:
        trend = kline.get("trend", 0)
        tech = 80 if trend > 0 else (40 if trend == 0 else 10)

    # 情绪/反身性：逆向——极度悲观=机会，高度一致看多=风险
    limit_up = market.get("limit_up_count", 0)
    adv = market.get("advance_ratio")
    if limit_up > 80 or (adv is not None and adv > 0.7):
        sent = 40  # 亢奋，一致性过高
    elif limit_up > 40 or (adv is not None and adv > 0.4):
        sent = 60
    else:
        sent = 100  # 冰点，反向机会

    # 风险：流动性 + 政策
    total_amount = market.get("total_amount", 0)
    limit_down = market.get("limit_down_count", 0)
    cfg = _get_scoring_config()
    liquidity_floor = cfg("experts.soros.market_liquidity_floor_yi", _SOROS_LIQUIDITY_FLOOR_DEFAULT)
    if total_amount > 0 and total_amount < liquidity_floor:
        risk = 20  # 流动性枯竭
    elif limit_down > 50:
        risk = 10
    elif limit_down > 20:
        risk = 40
    else:
        risk = 80

    return {"基本面": base, "估值": val, "技术面": tech, "情绪/反身性": sent, "风险": risk}
