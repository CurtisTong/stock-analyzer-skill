"""
质量因子评分：ROE、净利增速、营收增速、毛利率、负债率、经营现金流。
支持多期财务数据的 ROE 趋势判断。

2026 更新：新增 ESG/治理维度——分红记录、大股东减持、违规处罚、审计意见。
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

    # ROE 趋势：review#4 修复
    # 旧逻辑要求全序列严格单调（单期波动即打破），改为"下降期占比"
    roe_trend = fin.get("roe_trend", [])
    if len(roe_trend) >= 3:
        diffs = [roe_trend[i] - roe_trend[i - 1] for i in range(1, len(roe_trend))]
        decline_ratio = sum(1 for d in diffs if d < 0) / len(diffs)
        rise_ratio = sum(1 for d in diffs if d > 0) / len(diffs)
        if decline_ratio >= 0.6:  # 60% 以上期下降
            score -= 8  # 基本面恶化
        elif rise_ratio >= 0.6:  # 60% 以上期上升
            score += 5  # 基本面改善

    profit_growth_base = get_industry_threshold(industry, "profit_growth_excellent", 40)
    score += (
        clamp(profit_growth / profit_growth_base * 22) if profit_growth_base > 0 else 0
    )
    revenue_growth_base = get_industry_threshold(
        industry, "revenue_growth_excellent", 30
    )
    score += (
        clamp(revenue_growth / revenue_growth_base * 16)
        if revenue_growth_base > 0
        else 0
    )
    # 毛利率：相对于行业最低值评分
    if gross_margin_min > 0:
        score += clamp(gross_margin / (gross_margin_min * 2) * 16)
    else:
        score += clamp(gross_margin / 40 * 16)
    # 负债率：相对于行业上限评分
    score += clamp((debt_max + 10 - debt) / (debt_max + 10) * 12)
    if eps > 0 and cashflow > 0:
        score += clamp((cashflow / eps) * 6, 0, 6)

    # 盈利质量子维度（2026 新增）：区分高质量/低质量盈利
    score += _earnings_quality_score(fin, eps)

    # ESG/治理维度：合计 ±12 分（2026新增）
    score += _esg_score(fin)

    # A 股排雷维度：合计 ±10 分（v2.4.0 新增）
    score += _a_stock_red_flag_score(fin)

    return clamp(score)


def _earnings_quality_score(fin: dict, eps: float) -> float:
    """盈利质量子维度（±8 分）。

    维度：
    - 经营现金流/净利润比（+0~+4）：>0.8 利润含金量高
    - 应收账款/营收比（-2~+2）：<30% 收入质量好
    - 非经常性损益/净利润（-2~0）：<20% 利润真实
    """
    if not fin or eps <= 0:
        return 0

    eq_score = 0.0

    # 1. 经营现金流/净利润比（+0~+4）
    ocf = to_float(fin.get("ocf_per_share", fin.get("MGJYXJJE", 0)))
    if eps > 0 and ocf > 0:
        ocf_eps_ratio = ocf / eps
        if ocf_eps_ratio >= 1.2:
            eq_score += 4.0
        elif ocf_eps_ratio >= 0.8:
            eq_score += 3.0
        elif ocf_eps_ratio >= 0.5:
            eq_score += 1.5
        # <0.5 不加分

    # 2. 应收账款/营收比（-2~+2）
    revenue = to_float(fin.get("revenue", fin.get("TOTALOPERATEREVETZ", 0)))
    receivable = to_float(fin.get("accounts_receivable", fin.get("ACCOUNTS_RECE", 0)))
    if revenue > 0 and receivable > 0:
        ar_ratio = receivable / revenue * 100
        if ar_ratio < 15:
            eq_score += 2.0
        elif ar_ratio < 30:
            eq_score += 1.0
        elif ar_ratio > 60:
            eq_score -= 2.0
        elif ar_ratio > 45:
            eq_score -= 1.0

    # 3. 非经常性损益/净利润（-2~0）
    net_profit = to_float(fin.get("net_profit", fin.get("PARENTNETPROFIT", 0)))
    non_recurring = to_float(
        fin.get("non_recurring_gain", fin.get("DEDUCT_PARENTNETPROFIT", 0))
    )
    if net_profit > 0 and non_recurring != 0:
        nr_ratio = abs(non_recurring) / net_profit * 100
        if nr_ratio > 50:
            eq_score -= 2.0
        elif nr_ratio > 20:
            eq_score -= 1.0

    return clamp(eq_score, -8, 8)


def _esg_score(fin: dict) -> float:
    """ESG/治理维度评分（±12 分）。

    维度：
    - 分红记录（+0~+4）：连续分红 3/5/10 年分别加分
    - 大股东减持（-6~0）：近期大股东减持扣分
    - 违规处罚（-6~0）：近期被监管处罚扣分
    - 审计意见（-3~+2）：标准无保留意见加分，非标意见扣分
    """
    if not fin:
        return 0

    esg_score = 0.0

    # 1. 分红记录（+0~+4）
    consecutive_dividend = to_float(fin.get("consecutive_dividend_years", 0))
    if consecutive_dividend >= 10:
        esg_score += 4.0
    elif consecutive_dividend >= 5:
        esg_score += 2.5
    elif consecutive_dividend >= 3:
        esg_score += 1.0

    # 2. 大股东减持记录（-6~0）
    major_reduction = to_float(fin.get("major_shareholder_reduction", 0))
    if major_reduction > 5:  # 大股东减持超过 5%
        esg_score -= 6.0
    elif major_reduction > 2:  # 减持 2%-5%
        esg_score -= 3.0
    elif major_reduction > 0:  # 有小幅减持
        esg_score -= 1.0

    # 3. 违规处罚记录（-6~0）
    violation_penalty = to_float(fin.get("violation_penalty", 0))
    if violation_penalty >= 3:  # 3 次及以上违规
        esg_score -= 6.0
    elif violation_penalty >= 1:  # 1-2 次违规
        esg_score -= 3.0

    # 4. 审计意见（-3~+2）
    audit_opinion = str(fin.get("audit_opinion", "") or fin.get("AUDIT_OPINION", ""))
    if "标准无保留" in audit_opinion or "无保留" in audit_opinion:
        esg_score += 2.0
    elif "保留意见" in audit_opinion:
        esg_score -= 1.5
    elif "否定意见" in audit_opinion or "无法表示意见" in audit_opinion:
        esg_score -= 3.0

    return clamp(esg_score, -12, 12)


def _a_stock_red_flag_score(fin: dict) -> float:
    """A 股排雷维度（v2.4.0 新增，针对 A 股常见造假手法）。

    维度（合计 ±10 分）：
    - 商誉/净资产比（-4~0）：>30% 商誉减值风险高
    - 存贷双高（-4~0）：货币资金充裕但短期借款高，需警惕财务造假
    - 关联交易占比（-2~0）：相关收入/总营收 >30% 独立性差
    - 经营现金流/净利润持续背离（-2~+2）：<0.8 持续 2 年以上扣分

    数据字段：
    - goodwill / GOODWILL（商誉）
    - net_assets / TOTAL_EQUITY（净资产）
    - cash_and_equivalents / CASH_AND_EQUIVALENTS（货币资金）
    - short_term_borrowing / SHORT_BORROW（短期借款）
    - related_party_revenue / RELATED_REVENUE（关联收入）
    - total_revenue / TOTALOPERATEREVETZ（总营收）
    """
    if not fin:
        return 0

    flag_score = 0.0

    # 1. 商誉/净资产比（-4~0）
    goodwill = to_float(fin.get("goodwill", fin.get("GOODWILL", 0)))
    net_assets = to_float(fin.get("net_assets", fin.get("TOTAL_EQUITY", 0)))
    if net_assets > 0 and goodwill > 0:
        gw_ratio = goodwill / net_assets * 100
        if gw_ratio > 50:  # 商誉 > 净资产 50%
            flag_score -= 4.0
        elif gw_ratio > 30:
            flag_score -= 2.0

    # 2. 存贷双高（-4~0）
    # 货币资金充裕但短期借款高 → 财务造假信号（如康美药业、康得新）
    cash = to_float(fin.get("cash_and_equivalents", fin.get("CASH_AND_EQUIVALENTS", 0)))
    short_borrow = to_float(fin.get("short_term_borrowing", fin.get("SHORT_BORROW", 0)))
    if cash > 0 and short_borrow > 0:
        cash_borrow_ratio = cash / short_borrow
        # 货币资金 > 短期借款 2 倍且都有余额 → 存贷双高
        if cash_borrow_ratio > 2.0 and cash > 5e8:  # 5 亿阈值
            flag_score -= 4.0
        elif cash_borrow_ratio > 1.5:
            flag_score -= 1.5

    # 3. 关联交易占比（-2~0）
    related_rev = to_float(
        fin.get("related_party_revenue", fin.get("RELATED_REVENUE", 0))
    )
    total_rev = to_float(fin.get("total_revenue", fin.get("TOTALOPERATEREVETZ", 0)))
    if total_rev > 0 and related_rev > 0:
        related_pct = related_rev / total_rev * 100
        if related_pct > 50:
            flag_score -= 2.0
        elif related_pct > 30:
            flag_score -= 1.0

    # 4. 经营现金流/净利润背离（-2~+2）
    ocf = to_float(fin.get("ocf_per_share", fin.get("MGJYXJJE", 0)))
    eps = to_float(fin.get("eps", fin.get("EPSJB", 0)))
    if eps > 0 and ocf > 0:
        ocf_eps = ocf / eps
        if ocf_eps >= 1.0:
            flag_score += 2.0
        elif ocf_eps >= 0.7:
            flag_score += 0.5
        elif ocf_eps < 0.3:  # 现金流远低于净利润
            flag_score -= 2.0
        elif ocf_eps < 0.5:
            flag_score -= 1.0

    return clamp(flag_score, -10, 10)
