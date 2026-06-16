"""
行业专家评分函数 v2.1.1。

v2.1.0：骨架实现（调通用启发式 + 风险权重调整）
v2.1.1：保持骨架（TODO: 实现行业特异性阈值表）

人设：行业景气 + 竞争格局 + 估值差异。
TODO 项：
- 不同行业用不同阈值（医药 PE=30 合理，半导体 PE=30 可能泡沫）
- 行业景气度指标（行业 PE 分位 / 板块涨跌排名）
- 竞争格局指标（CR3 / CR5 / 市占率）
"""
from typing import Dict


def score(stock_data: dict) -> Dict[str, float]:
    """行业专家专属评分（骨架，调通用启发式 + 风险权重）。"""
    from . import _score_fundamentals, _score_valuation, _score_technical, _score_sentiment
    fin = stock_data.get("finance") or {}
    quote = stock_data.get("quote") or {}
    kline_features = stock_data.get("kline_features") or {}
    market_features = stock_data.get("market_features") or {}

    return {
        "基本面": _score_fundamentals(fin),
        "估值": _score_valuation(quote, fin),
        "技术面": _score_technical(kline_features),
        "情绪": min(100, max(0, _score_sentiment(market_features) * 0.6)),
        "风险": round(_score_fundamentals(fin) * 0.4 + _score_valuation(quote, fin) * 0.3 +
                       (100 - float(fin.get("debt_ratio") or fin.get("ZCFZL") or 50)) * 0.3, 1),
    }
