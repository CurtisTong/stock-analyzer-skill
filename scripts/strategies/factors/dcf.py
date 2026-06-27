"""DCF（折现现金流）简易估值模型。

两阶段 DCF：
- 阶段 1（1-5 年）：高增长期，使用分析师预期增速或历史增速
- 阶段 2（6-10 年）：过渡期，增速逐年递减至永续增长率

输出：内在价值 vs 市价的偏离度（正数 = 低估，负数 = 高估）。

注意：A 股 FCF 数据不完整，本模型使用以下近似：
- FCF = 经营现金流 - 资本支出（如有）
- 回退到 净利润 × 0.7（保守估计）
"""

from common import to_float


def dcf_valuation(
    price: float,
    fin: dict,
    growth_rate: float = None,
    discount_rate: float = 0.10,
    terminal_growth: float = 0.03,
    years_high: int = 5,
    years_transition: int = 5,
    industry: str = "默认",
) -> dict:
    """两阶段 DCF 估值。

    Args:
        price: 当前股价
        fin: 财务 dict（需含 eps/ocf_per_share/capex 等）
        growth_rate: 预期增长率（小数，如 0.15 = 15%）。None 则自动推断
        industry: 行业类型（用于差异化资本支出系数）
        discount_rate: 折现率（WACC 近似，默认 10%）
        terminal_growth: 永续增长率（默认 3%）
        years_high: 高增长期年数（默认 5）
        years_transition: 过渡期年数（默认 5）

    Returns:
        {
            "intrinsic_value": 内在价值,
            "price": 当前价,
            "margin_of_safety": 安全边际（正数=低估）,
            "fcf_per_share": 每股自由现金流,
            "growth_rate": 使用的增长率,
            "method": "dcf",
        }
    """
    # 行业差异化资本支出系数
    # 重资产行业（钢铁/化工/机械）资本支出大，FCF/OCF 比例低
    # 轻资产行业（软件/医药/消费）资本支出小，FCF/OCF 比例高
    _CAPEX_RATIO = {
        "重资产": 0.5,
        "周期": 0.55,
        "默认": 0.7,
        "消费": 0.75,
        "科技": 0.8,
        "医药": 0.8,
        "金融": 0.85,
    }
    capex_ratio = _CAPEX_RATIO.get(industry, _CAPEX_RATIO["默认"])

    # 1. 估算每股自由现金流（FCF）
    ocf = to_float(fin.get("ocf_per_share", fin.get("MGJYXJJE", 0)))
    eps = to_float(fin.get("eps", fin.get("EPSJB", 0)))

    if ocf > 0:
        # 有经营现金流数据时，用 OCF × 行业系数
        fcf_per_share = ocf * capex_ratio
    elif eps > 0:
        # 回退到净利润 × 行业系数
        fcf_per_share = eps * capex_ratio
    else:
        return {
            "intrinsic_value": 0,
            "price": price,
            "margin_of_safety": -100,
            "fcf_per_share": 0,
            "growth_rate": 0,
            "method": "dcf",
            "error": "无可用现金流数据",
        }

    # 2. 推断增长率
    if growth_rate is None:
        # 优先用 3 年复合增速
        cagr_3y = to_float(fin.get("net_profit_cagr_3y", 0))
        if cagr_3y > 0:
            growth_rate = cagr_3y / 100
        else:
            # 用单期增速
            profit_yoy = to_float(
                fin.get("net_profit_yoy", fin.get("PARENTNETPROFITTZ", 0))
            )
            if profit_yoy > 0:
                growth_rate = min(profit_yoy / 100, 0.30)  # 上限 30%
            else:
                growth_rate = 0.05  # 默认 5%

    # 增长率合理性约束
    growth_rate = max(0.01, min(growth_rate, 0.30))  # 1%-30%

    # 3. 两阶段 DCF 计算
    total_value = 0
    current_fcf = fcf_per_share

    # 阶段 1：高增长期
    for year in range(1, years_high + 1):
        pv = current_fcf / ((1 + discount_rate) ** year)
        total_value += pv
        current_fcf *= 1 + growth_rate

    # 阶段 2：过渡期（增速逐年递减）
    for year in range(1, years_transition + 1):
        # 增速从 growth_rate 线性递减到 terminal_growth
        transition_growth = (
            growth_rate - (growth_rate - terminal_growth) * year / years_transition
        )
        pv = current_fcf / ((1 + discount_rate) ** (years_high + year))
        total_value += pv
        current_fcf *= 1 + transition_growth

    # 永续价值（Gordon Growth Model）
    terminal_value = current_fcf / (discount_rate - terminal_growth)
    terminal_pv = terminal_value / (
        (1 + discount_rate) ** (years_high + years_transition)
    )
    total_value += terminal_pv

    intrinsic_value = round(total_value, 2)
    margin_of_safety = (
        round((intrinsic_value - price) / price * 100, 1) if price > 0 else 0
    )

    return {
        "intrinsic_value": intrinsic_value,
        "price": price,
        "margin_of_safety": margin_of_safety,
        "fcf_per_share": round(fcf_per_share, 2),
        "growth_rate": round(growth_rate * 100, 1),
        "discount_rate": round(discount_rate * 100, 1),
        "terminal_growth": round(terminal_growth * 100, 1),
        "method": "dcf",
    }


def dcf_score(price: float, fin: dict, industry: str = "默认") -> float:
    """DCF 估值评分（0-100，50=合理估值）。

    基于安全边际打分：
    - 安全边际 > 50%: 90 分（极度低估）
    - 安全边际 20-50%: 70 分（明显低估）
    - 安全边际 0-20%: 55 分（轻微低估）
    - 安全边际 -20%-0%: 40 分（轻微高估）
    - 安全边际 < -20%: 20 分（明显高估）
    """
    result = dcf_valuation(price, fin)
    margin = result.get("margin_of_safety", -100)

    if result.get("error"):
        return 50  # 无数据给中性分

    if margin > 50:
        return 90
    elif margin > 20:
        return 70
    elif margin > 0:
        return 55
    elif margin > -20:
        return 40
    else:
        return 20


# ═══════════════════════════════════════════════════════════════
# EV/EBITDA 估值（企业价值/息税折旧摊销前利润）
# ═══════════════════════════════════════════════════════════════


def ev_ebitda_valuation(
    price: float,
    fin: dict,
    quote: dict = None,
) -> dict:
    """EV/EBITDA 估值。

    EV = 市值 + 有息负债 - 现金
    EBITDA ≈ 净利润 + 所得税 + 利息 + 折旧摊销（近似：净利润 / (1-税率) + 折旧）

    A 股数据限制：折旧摊销数据不完整，使用以下近似：
    - EBITDA ≈ 营业利润 × 1.3（粗略估计折旧摊销占比）
    - 回退到 EPS × 总股本 × 1.3

    Args:
        price: 当前股价
        fin: 财务 dict
        quote: 行情 dict（含 total_cap）

    Returns:
        {
            "ev_ebitda": EV/EBITDA 比值,
            "ev": 企业价值,
            "ebitda": EBITDA,
            "method": "ev_ebitda",
        }
    """
    # 市值（亿元）
    total_cap = to_float((quote or {}).get("total_cap", 0))

    # 简化：EV ≈ 市值（忽略有息负债和现金，A 股数据不完整）
    ev = total_cap

    # EBITDA 近似
    # 方式 1：用营业利润
    operating_profit = to_float(fin.get("operating_profit", fin.get("YYLR", 0)))
    if operating_profit > 0:
        ebitda = operating_profit * 1.3  # 粗略估计折旧摊销占比 30%
    else:
        # 方式 2：用 EPS × 1.3
        eps = to_float(fin.get("eps", fin.get("EPSJB", 0)))
        if eps > 0 and total_cap > 0:
            # total_cap 是亿元，price 是元
            shares = total_cap * 1e8 / price if price > 0 else 0
            ebitda = eps * shares * 1.3 / 1e8  # 转回亿元
        else:
            return {
                "ev_ebitda": 0,
                "ev": ev,
                "ebitda": 0,
                "method": "ev_ebitda",
                "error": "无可用 EBITDA 数据",
            }

    if ebitda <= 0:
        return {
            "ev_ebitda": 0,
            "ev": ev,
            "ebitda": 0,
            "method": "ev_ebitda",
            "error": "EBITDA 为负或零",
        }

    ev_ebitda = round(ev / ebitda, 2)

    return {
        "ev_ebitda": ev_ebitda,
        "ev": round(ev, 2),
        "ebitda": round(ebitda, 2),
        "method": "ev_ebitda",
    }


def ev_ebitda_score(
    price: float, fin: dict, quote: dict = None, industry: str = "默认"
) -> float:
    """EV/EBITDA 估值评分（0-100，50=合理估值）。

    行业差异化阈值：
    - < 8: 低估（70 分）
    - 8-12: 合理（50 分）
    - 12-18: 偏高（35 分）
    - > 18: 高估（20 分）
    """
    from strategies.thresholds import get_industry_threshold

    result = ev_ebitda_valuation(price, fin, quote)

    if result.get("error"):
        return 50  # 无数据给中性分

    ratio = result["ev_ebitda"]
    low = get_industry_threshold(industry, "ev_ebitda_low", 8)
    mid = get_industry_threshold(industry, "ev_ebitda_mid", 12)
    high = get_industry_threshold(industry, "ev_ebitda_high", 18)

    if ratio <= 0:
        return 50
    elif ratio < low:
        return 70
    elif ratio < mid:
        return 50
    elif ratio < high:
        return 35
    else:
        return 20
