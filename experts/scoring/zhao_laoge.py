"""
赵老哥专属评分函数。

维度：基本面(10%) + 估值(12%) + 技术面(31%) + 情绪/题材(35%) + 风险(12%)
精确复现 experts/zhao_laoge.md §九 评分矩阵中的阈值规则。

# P1-11 已知数据缺失（详见 decide.md §八）：
# 1. 龙头地位：persona 定义为"龙头地位"（稳固->100，被替代->0，跌破20日线->否决），
#    代码用"回撤至 MA20 深度"近似（>=0->80，>=-8->30，else 10），因龙头地位需板块横截面
#    排名数据（同题材涨幅排名），当前数据源不提供。回撤深度与龙头强度弱相关。
# 2. 龙虎榜数据：未接入任何 scoring 模块（data/lhb 模块存在但 experts/scoring/ 无消费），
#    涨停板资金博弈信号缺失。接入属 P2 范畴。
"""

import statistics
from typing import Dict

from ._utils import _safe_float


def score(stock_data: dict) -> Dict[str, float]:
    """赵老哥专属评分：均线排列 + 题材生命周期 + 流通市值。"""
    quote = stock_data.get("quote") or {}
    kline = stock_data.get("kline_features") or {}
    kline_data = stock_data.get("kline_data") or {}
    market = stock_data.get("market_features") or {}

    # 基本面：题材容量/政策支持度（zhao_laoge.md §九：国家战略级->100，产业级->60，无题材->0）
    # 优先读 market_features.topic_tier（0=无/1=产业级/2=国家战略级）；
    # 次选涨停基因（近30日涨停次数）作题材强度代理；缺数据回退中性 50。
    topic_tier = market.get("topic_tier")
    limit_up_30d = _safe_float(market.get("limit_up_30d") or quote.get("limit_up_30d"))
    if topic_tier is not None:
        if topic_tier >= 2:
            base = 100
        elif topic_tier >= 1:
            base = 60
        else:
            base = 0
    elif limit_up_30d > 0:
        base = 60  # 有涨停基因，视为有题材
    else:
        base = 50  # 缺题材数据，回退中性

    # 估值：流通市值
    circ_cap = _safe_float(quote.get("circulating_cap"))
    if 50 <= circ_cap <= 300:
        val = 100
    elif 30 <= circ_cap <= 500:
        val = 60
    elif circ_cap > 1000:
        val = 20
    else:
        val = 50

    # 技术面：均线系统
    closes = kline_data.get("closes") or []
    if len(closes) >= 20:
        ma5 = statistics.mean(closes[-5:])
        ma10 = statistics.mean(closes[-10:])
        ma20 = statistics.mean(closes[-20:])
        if ma5 > ma10 > ma20:
            tech = 100
        elif ma5 < ma10 < ma20:
            tech = 0
        else:
            tech = 70
    else:
        trend = kline.get("trend", 0)
        tech = 80 if trend > 0 else (40 if trend == 0 else 10)

    # 情绪/题材：量价配合
    volumes = kline_data.get("volumes") or []
    if len(closes) >= 10 and len(volumes) >= 10:
        recent_vol = statistics.mean(volumes[-5:])
        prev_vol = statistics.mean(volumes[-10:-5])
        if recent_vol > prev_vol * 1.2 and closes[-1] > statistics.mean(closes[-5:-1]):
            sent = 100
        elif recent_vol < prev_vol * 0.8:
            sent = 60
        else:
            sent = 40
    else:
        sent = 50

    # 风险：龙头地位 + 20日均线（渐进式扣分，龙头低吸风格破20日线常是买点）
    if len(closes) >= 20:
        ma20 = statistics.mean(closes[-20:])
        if ma20 > 0:
            pullback_pct = (closes[-1] - ma20) / ma20 * 100
            if pullback_pct >= 0:
                risk = 80
            elif pullback_pct >= -3:
                risk = 60
            elif pullback_pct >= -8:
                risk = 30
            else:
                risk = 10
        else:
            risk = 50
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
    """赵老哥评分（含推理链）。

    v2.2.0 起统一使用 generic_score_with_reasoning 模板。
    """
    from experts.registry import EXPERT_REGISTRY
    from ._utils import generic_score_with_reasoning

    profile = EXPERT_REGISTRY["zhao_laoge"]
    return generic_score_with_reasoning(profile, score, stock_data)
