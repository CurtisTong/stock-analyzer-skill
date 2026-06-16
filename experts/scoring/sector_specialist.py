"""
行业专家评分函数。

人设：行业景气 + 竞争格局 + 估值差异。
当前为最小骨架实现。
"""
from typing import Dict


def score(stock_data: dict) -> Dict[str, float]:
    """行业专家专属评分（暂用通用启发式）。"""
    from . import _score_fundamentals, _score_valuation, _score_technical, _score_sentiment
    fin = stock_data.get("finance") or {}
    quote = stock_data.get("quote") or {}
    kline_features = stock_data.get("kline_features") or {}
    market_features = stock_data.get("market_features") or {}

    return {
        "基本面": _score_fundamentals(fin),
        "估值": _score_valuation(quote, fin),
        "技术面": _score_technical(kline_features),
        "情绪": _score_sentiment(market_features) * 0.6,
        "风险": round(_score_fundamentals(fin) * 0.4 + _score_valuation(quote, fin) * 0.3 +
                       (100 - float(fin.get("debt_ratio") or fin.get("ZCFZL") or 50)) * 0.3, 1),
    }
