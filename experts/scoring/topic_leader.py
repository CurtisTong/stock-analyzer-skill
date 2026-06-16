"""
题材龙头（合并徐翔+赵老哥）评分函数。

人设：涨停板战法 + 趋势龙头，强调量价+情绪/题材。
当前为最小骨架实现。
"""
from typing import Dict


def score(stock_data: dict) -> Dict[str, float]:
    """题材龙头专属评分。"""
    from . import _score_fundamentals, _score_valuation, _score_technical, _score_sentiment
    fin = stock_data.get("finance") or {}
    quote = stock_data.get("quote") or {}
    kline_features = stock_data.get("kline_features") or {}
    market_features = stock_data.get("market_features") or {}

    return {
        "基本面": min(100, max(0, _score_fundamentals(fin) * 0.5 + 25)),  # 基本面权重低（7.5%）
        "估值": _score_valuation(quote, fin),
        "技术面": min(100, max(0, _score_technical(kline_features) * 1.2)),  # 技术面权重高（30.5%）
        "情绪/题材": _score_sentiment(market_features),
        "风险": round(_score_fundamentals(fin) * 0.4 + _score_valuation(quote, fin) * 0.3 +
                       (100 - float(fin.get("debt_ratio") or fin.get("ZCFZL") or 50)) * 0.3, 1),
    }
