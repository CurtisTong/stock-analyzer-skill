"""
质量因子评分：ROE、净利增速、营收增速、毛利率、负债率、经营现金流。
"""
from common import to_float, clamp
from strategies.thresholds import get_industry_threshold


def quality_score(fin: dict, industry: str = "默认") -> float:
    """质量因子评分（行业差异化）。满分 100。"""
    roe = to_float(fin.get("ROEJQ"))
    profit_growth = to_float(fin.get("PARENTNETPROFITTZ"))
    revenue_growth = to_float(fin.get("TOTALOPERATEREVETZ"))
    gross_margin = to_float(fin.get("XSMLL"))
    debt = to_float(fin.get("ZCFZL"))
    eps = to_float(fin.get("EPSJB"))
    cashflow = to_float(fin.get("MGJYXJJE"))

    # 行业差异化 ROE 基准
    roe_excellent = get_industry_threshold(industry, "roe_excellent", 20)
    gross_margin_min = get_industry_threshold(industry, "gross_margin_min", 20)
    debt_max = get_industry_threshold(industry, "debt_ratio_max", 60)

    score = 0
    # ROE：相对于行业优秀值评分
    score += clamp(roe / roe_excellent * 28)
    score += clamp(profit_growth / 40 * 22)
    score += clamp(revenue_growth / 30 * 16)
    # 毛利率：相对于行业最低值评分
    if gross_margin_min > 0:
        score += clamp(gross_margin / (gross_margin_min * 2) * 16)
    else:
        score += clamp(gross_margin / 40 * 16)
    # 负债率：相对于行业上限评分
    score += clamp((debt_max + 10 - debt) / (debt_max + 10) * 12)
    if eps > 0 and cashflow > 0:
        score += clamp((cashflow / eps) * 6, 0, 6)
    return clamp(score)
