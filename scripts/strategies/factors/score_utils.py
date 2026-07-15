"""因子评分公共工具：PE 估值、ScoringContext。"""

from dataclasses import dataclass


def pe_percentile(pe: float, industry: str = "默认") -> float:
    """PE 百分位估值（0-100）。统一实现，消除 3 处重复。

    Args:
        pe: 市盈率
        industry: 行业名称

    Returns:
        0-100 的百分位值，越高表示越贵
    """
    from strategies.thresholds import get_industry_threshold

    pe_low = get_industry_threshold(industry, "pe_undervalued", 15)
    pe_mid = get_industry_threshold(industry, "pe_reasonable", 25)
    pe_high = get_industry_threshold(industry, "pe_expensive", 40)

    if pe <= 0:
        return 50
    if pe <= pe_low:
        return 15
    if pe <= pe_mid:
        return 15 + (pe - pe_low) / (pe_mid - pe_low) * 35
    if pe <= pe_high:
        return 50 + (pe - pe_mid) / (pe_high - pe_mid) * 30
    return min(95, 80 + (pe - pe_high) / pe_high * 20)


@dataclass
class ScoringContext:
    """因子评分上下文。"""

    quote: dict
    fin: dict
    features: dict
    industry: str = "默认"
    code: str = ""
