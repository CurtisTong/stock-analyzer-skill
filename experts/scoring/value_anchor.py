"""
价值双锚（合并巴菲特+段永平）评分函数。

人设：美式数据 + 中式文化，强调 ROE/PE + 商业模式 + 安全边际。
当前为最小骨架实现，调通用 score_expert() 作为 fallback。
"""
from typing import Dict


def score(stock_data: dict) -> Dict[str, float]:
    """价值双锚专属评分。"""
    # TODO: 实现专属阈值（暂用通用启发式）
    from . import _score_fundamentals, _score_valuation, _score_technical, _score_sentiment
    fin = stock_data.get("finance") or {}
    quote = stock_data.get("quote") or {}
    kline_features = stock_data.get("kline_features") or {}
    market_features = stock_data.get("market_features") or {}

    debt = float(fin.get("debt_ratio") or fin.get("ZCFZL") or 50)
    margin_of_safety = round((_score_valuation(quote, fin) * 0.5 + _score_fundamentals(fin) * 0.5) * 0.85, 1)

    return {
        "基本面": _score_fundamentals(fin),
        "估值": _score_valuation(quote, fin),
        "技术面": _score_technical(kline_features),
        "情绪": _score_sentiment(market_features),
        "安全边际": margin_of_safety,
    }
