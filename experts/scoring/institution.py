"""
机构派评分函数。

人设：深度尽调 + 长期持有 + 集中持仓。
当前为最小骨架实现。
"""
from typing import Dict


def score(stock_data: dict) -> Dict[str, float]:
    """机构派专属评分（暂用通用启发式）。"""
    from . import _score_fundamentals, _score_valuation, _score_technical, _score_sentiment
    fin = stock_data.get("finance") or {}
    quote = stock_data.get("quote") or {}
    kline_features = stock_data.get("kline_features") or {}
    market_features = stock_data.get("market_features") or {}

    return {
        "基本面": _score_fundamentals(fin),
        "估值": _score_valuation(quote, fin),
        "技术面": min(100, max(0, _score_technical(kline_features) * 0.5 + 25)),
        "情绪": min(100, max(0, _score_sentiment(market_features) * 0.5 + 25)),
        "安全边际": (_score_valuation(quote, fin) * 0.5 + _score_fundamentals(fin) * 0.5),
    }
