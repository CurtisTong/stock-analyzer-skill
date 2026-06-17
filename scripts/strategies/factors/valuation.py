"""
估值因子评分：PE、PB、PEG、PS（市销率）。
PS 对亏损但有收入的公司是唯一可用的估值指标。
"""

from common import to_float, clamp
from strategies.thresholds import get_industry_threshold


def valuation_score(quote: dict, fin: dict, industry: str = "默认") -> float:
    """估值因子评分（行业差异化）。满分 100。"""
    pe = to_float(quote.get("pe"))
    pb = to_float(quote.get("pb"))
    growth = max(to_float(fin.get("net_profit_yoy", fin.get("PARENTNETPROFITTZ"))), 0)

    # 亏损股评分用到的字段
    total_cap = to_float(quote.get("total_cap"))  # 亿
    revenue_yoy = to_float(fin.get("revenue_yoy", fin.get("TOTALOPERATEREVETZ")))

    # 行业差异化 PE 阈值
    pe_undervalued = get_industry_threshold(industry, "pe_undervalued", 15)
    pe_reasonable = get_industry_threshold(industry, "pe_reasonable", 25)
    pe_expensive = get_industry_threshold(industry, "pe_expensive", 40)
    peg_undervalued = get_industry_threshold(industry, "peg_undervalued", 0.8)
    peg_reasonable = get_industry_threshold(industry, "peg_reasonable", 1.5)

    # PE 极端值截断：超过行业 expensive 阈值 2 倍时，PE 评分为 0
    pe_cap = pe_expensive * 2

    score = 0
    # PE 评分（行业差异化）
    if pe <= 0:
        # 亏损股评分：不重复计算 PB（PB 在下方通用段评分）
        # 亏损收窄加分（净利润同比为正 = 亏损在收窄）
        if growth > 0:
            score += 12
        # PS 评分：用营收增速作为市销率 proxy
        # 逻辑：高增速亏损公司（如科创板早期）PS 视角可接受
        # 低增速亏损公司（传统行业）PS 估值无意义
        if revenue_yoy > 0:
            if revenue_yoy > 30:
                score += 20  # 高增长亏损，PS 视角可接受
            elif revenue_yoy > 10:
                score += 12  # 中等增长
            else:
                score += 5  # 低增长，给基础分
        # 大市值亏损惩罚：大公司亏损通常意味着基本面恶化
        if total_cap > 100 and revenue_yoy <= 0:
            score -= 8
    elif pe > pe_cap:
        # PE 超过极端阈值，PE 评分为 0（但 PB 和 PEG 仍可评分）
        pass
    elif 0 < pe <= pe_undervalued:
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

    # PEG 评分（仅盈利股，且 PE 未超极端阈值）
    # review#5 修复：优先用 3 年复合增速（净利 CAGR），避免单期增速被基数效应扭曲
    if 0 < pe <= pe_cap and growth > 0:
        growth_3y = to_float(fin.get("net_profit_cagr_3y", 0))
        peg_growth = growth_3y if growth_3y > 0 else growth
        if peg_growth > 0:
            peg = pe / peg_growth
            if peg <= peg_undervalued:
                score += 28
            elif peg <= peg_reasonable:
                score += 22
            elif peg <= peg_reasonable * 1.5:
                score += 12

    return clamp(score)
