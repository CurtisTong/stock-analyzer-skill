"""
情绪技术复合（合并炒股养家+作手新一）评分函数。

人设：情绪周期 + K线反转形态。
当前为最小骨架实现。
"""
from typing import Dict


def score(stock_data: dict) -> Dict[str, float]:
    """情绪技术复合专属评分。"""
    from . import _score_fundamentals, _score_valuation, _score_technical, _score_sentiment
    fin = stock_data.get("finance") or {}
    quote = stock_data.get("quote") or {}
    kline_features = stock_data.get("kline_features") or {}
    market_features = stock_data.get("market_features") or {}

    return {
        "基本面": min(100, max(0, _score_fundamentals(fin) * 0.4 + 30)),  # 基础 6.5% 权重
        "估值": _score_valuation(quote, fin),
        "技术面": _score_technical(kline_features),
        "情绪": min(100, max(0, _score_sentiment(market_features) * 1.4)),  # 情绪权重最高（46.5%）
        "风险": round(_score_fundamentals(fin) * 0.4 + _score_valuation(quote, fin) * 0.3 +
                       (100 - float(fin.get("debt_ratio") or fin.get("ZCFZL") or 50)) * 0.3, 1),
    }
