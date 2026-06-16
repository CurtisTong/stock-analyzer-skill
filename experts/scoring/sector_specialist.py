"""
行业专家评分函数 v2.1.2。

v2.1.0：骨架实现
v2.1.1：明确 TODO 标注
v2.1.2：实现"行业 PE 分位 + 行业景气 + 竞争格局代理"完整版

人设：行业景气 + 竞争格局 + 估值差异。
核心逻辑：
- 行业估值水位：pe_percentile 越低越好（行业低估加分）
- 行业景气：ROE + 营收增速（持续优秀 = 行业龙头）
- 竞争格局：低负债率 = 龙头优势（护城河）
- 风险预警：PE 行业分位 >80% 减分（行业泡沫）
"""
from typing import Dict

from ._utils import _safe_float


def score(stock_data: dict) -> Dict[str, float]:
    """行业专家专属评分。

    维度：基本面（行业景气）+ 估值（行业 PE 分位）+ 风险（竞争格局）。
    """
    from . import _score_fundamentals, _score_valuation, _score_technical, _score_sentiment
    fin = stock_data.get("finance") or {}
    quote = stock_data.get("quote") or {}
    kline_features = stock_data.get("kline_features") or {}
    market_features = stock_data.get("market_features") or {}

    # ── 基本面：行业景气（ROE + 营收增速 双高 = 行业龙头）──
    roe = _safe_float(fin.get("ROEJQ") or fin.get("roe"))
    rev_yoy = _safe_float(fin.get("TOTALOPERATEREVETZ") or fin.get("revenue_yoy"))
    if roe >= 20 and rev_yoy >= 15:
        sector_prosperity = 95  # 高景气
    elif roe >= 15 and rev_yoy >= 10:
        sector_prosperity = 75
    elif roe >= 10:
        sector_prosperity = 55
    else:
        sector_prosperity = 25  # 行业衰退

    # ── 估值：行业 PE 分位（区分"绝对 PE 高"和"行业水位高"）──
    pe = _safe_float(quote.get("pe"))
    pe_pct = _safe_float(quote.get("pe_percentile"), 50)
    pb = _safe_float(quote.get("pb"))
    if 0 <= pe_pct <= 20:
        # 行业低估区间——高分
        sector_valuation = 90
    elif 20 < pe_pct <= 40:
        sector_valuation = 70
    elif 40 < pe_pct <= 60:
        sector_valuation = 55  # 中位
    elif 60 < pe_pct <= 80:
        sector_valuation = 35
    else:
        # 行业高估区间——低分（但 PE 绝对值合理时不扣太多）
        sector_valuation = 20 if pe > 100 else 30

    # ── 技术面：行业趋势 ──
    sector_tech = _score_technical(kline_features)

    # ── 情绪：行业情绪（弱化版）──
    sector_sentiment = min(100, max(0, _score_sentiment(market_features) * 0.6))

    # ── 风险：竞争格局代理（低负债 + 高 ROE = 龙头护城河）──
    debt = _safe_float(fin.get("ZCFZL") or fin.get("debt_ratio"), 50)
    if debt < 30 and roe >= 15:
        competitive_moat = 90  # 强护城河
    elif debt < 50 and roe >= 10:
        competitive_moat = 65
    elif debt > 70:
        competitive_moat = 20  # 高杠杆风险
    else:
        competitive_moat = 45

    return {
        "基本面": sector_prosperity,
        "估值": sector_valuation,
        "技术面": sector_tech,
        "情绪": sector_sentiment,
        "风险": competitive_moat,
    }