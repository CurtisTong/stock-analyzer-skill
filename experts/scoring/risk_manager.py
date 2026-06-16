"""
风险管理评分函数。

人设：二阶思维 + 周期位置 + 风险预算。
当前为最小骨架实现。
"""
from typing import Dict


def score(stock_data: dict) -> Dict[str, float]:
    """风险管理专属评分。"""
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
