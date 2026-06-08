"""
质量因子评分：ROE、净利增速、营收增速、毛利率、负债率、经营现金流。
支持多期财务数据的 ROE 趋势判断。
"""
from common import to_float, clamp
from strategies.thresholds import get_industry_threshold


def quality_score(fin: dict, industry: str = "默认") -> float:
    """质量因子评分（行业差异化）。满分 100。
    fin 可包含多期数据（roe_trend 列表），用于 ROE 趋势判断。
    """
    # 支持标准化字段名（data层）和原始东财字段名（兼容）
    roe = to_float(fin.get("roe", fin.get("ROEJQ")))
    profit_growth = to_float(fin.get("net_profit_yoy", fin.get("PARENTNETPROFITTZ")))
    revenue_growth = to_float(fin.get("revenue_yoy", fin.get("TOTALOPERATEREVETZ")))
    gross_margin = to_float(fin.get("gross_margin", fin.get("XSMLL")))
    debt = to_float(fin.get("debt_ratio", fin.get("ZCFZL")))
    eps = to_float(fin.get("eps", fin.get("EPSJB")))
    cashflow = to_float(fin.get("ocf_per_share", fin.get("MGJYXJJE")))

    # 行业差异化 ROE 基准
    roe_excellent = get_industry_threshold(industry, "roe_excellent", 20)
    gross_margin_min = get_industry_threshold(industry, "gross_margin_min", 20)
    debt_max = get_industry_threshold(industry, "debt_ratio_max", 60)

    score = 0
    # ROE：相对于行业优秀值评分
    score += clamp(roe / roe_excellent * 28)

    # ROE 趋势：连续下降扣分，连续上升加分
    roe_trend = fin.get("roe_trend", [])
    if len(roe_trend) >= 2:
        declining = all(roe_trend[i] < roe_trend[i - 1] for i in range(1, len(roe_trend)))
        rising = all(roe_trend[i] > roe_trend[i - 1] for i in range(1, len(roe_trend)))
        if declining:
            score -= 8  # ROE 连续下降，基本面恶化信号
        elif rising:
            score += 5  # ROE 连续上升，基本面改善

    profit_growth_base = get_industry_threshold(industry, "profit_growth_excellent", 40)
    score += clamp(profit_growth / profit_growth_base * 22) if profit_growth_base > 0 else 0
    revenue_growth_base = get_industry_threshold(industry, "revenue_growth_excellent", 30)
    score += clamp(revenue_growth / revenue_growth_base * 16) if revenue_growth_base > 0 else 0
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
