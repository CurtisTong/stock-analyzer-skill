"""
风险管理评分函数 v2.1.1。

v2.1.0：骨架实现
v2.1.1：保持骨架（TODO: 实现周期位置检测）

人设：二阶思维 + 周期位置 + 风险预算。
TODO 项：
- 市场周期位置指标（PE 历史分位 + M2 同比 + 社融）
- 风险预算（组合集中度 + 杠杆率）
- 二阶思维指标（市场情绪温度 / 逆向信号）
"""
from typing import Dict


def score(stock_data: dict) -> Dict[str, float]:
    """风险管理专属评分（骨架）。"""
    from . import _score_fundamentals, _score_valuation, _score_technical, _score_sentiment
    fin = stock_data.get("finance") or {}
    quote = stock_data.get("quote") or {}
    kline_features = stock_data.get("kline_features") or {}
    market_features = stock_data.get("market_features") or {}

    debt = float(fin.get("debt_ratio") or fin.get("ZCFZL") or 50)
    return {
        "基本面": _score_fundamentals(fin),
        "估值": _score_valuation(quote, fin),
        "技术面": _score_technical(kline_features),
        "情绪": _score_sentiment(market_features),
        "风险": round(_score_fundamentals(fin) * 0.25 + _score_valuation(quote, fin) * 0.25 +
                       (100 - debt) * 0.5, 1),
    }
