"""
机构派评分函数 v2.1.1。

v2.1.0：骨架实现（调通用启发式 + 技术/情绪降权）
v2.1.1：保持骨架（TODO: 实现尽调指标）

人设：深度尽调 + 长期持有 + 集中持仓。
TODO 项：
- 公司治理指标（管理层诚信 / 股权结构 / 关联交易）
- 行业空间指标（天花板 / CAGR）
- 管理层激励（股权激励 / 期权计划）
"""
from typing import Dict


def score(stock_data: dict) -> Dict[str, float]:
    """机构派专属评分（骨架，调通用启发式 + 技术/情绪降权）。"""
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
