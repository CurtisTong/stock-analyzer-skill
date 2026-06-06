"""
估值因子评分：PE、PB、PEG。
"""
from common import to_float, clamp
from strategies.thresholds import get_industry_threshold


def valuation_score(quote: dict, fin: dict, industry: str = "默认") -> float:
    """估值因子评分（行业差异化）。满分 100。"""
    pe = to_float(quote.get("pe"))
    pb = to_float(quote.get("pb"))
    growth = max(to_float(fin.get("net_profit_yoy", fin.get("PARENTNETPROFITTZ"))), 0)

    # 行业差异化 PE 阈值
    pe_undervalued = get_industry_threshold(industry, "pe_undervalued", 15)
    pe_reasonable = get_industry_threshold(industry, "pe_reasonable", 25)
    pe_expensive = get_industry_threshold(industry, "pe_expensive", 40)
    peg_undervalued = get_industry_threshold(industry, "peg_undervalued", 0.8)
    peg_reasonable = get_industry_threshold(industry, "peg_reasonable", 1.5)

    score = 0
    # PE 评分（行业差异化）
    if 0 < pe <= pe_undervalued:
        score += 38
    elif pe_undervalued < pe <= pe_reasonable:
        score += 38 - (pe - pe_undervalued) / (pe_reasonable - pe_undervalued) * 18
    elif pe_reasonable < pe <= pe_expensive:
        score += 20 - (pe - pe_reasonable) / (pe_expensive - pe_reasonable) * 10

    # PB 评分
    if 0 < pb <= 2:
        score += 24
    elif 2 < pb <= 5:
        score += 24 - (pb - 2) / 3 * 14

    # PEG 评分（行业差异化）
    if pe > 0 and growth > 0:
        peg = pe / growth
        if peg <= peg_undervalued:
            score += 28
        elif peg <= peg_reasonable:
            score += 22
        elif peg <= peg_reasonable * 1.5:
            score += 12

    return clamp(score)
