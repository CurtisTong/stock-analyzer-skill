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
) -> dict:
    """两阶段 DCF 估值。

    Args:
        price: 当前股价
        fin: 财务 dict（需含 eps/ocf_per_share/capex 等）
        growth_rate: 预期增长率（小数，如 0.15 = 15%）。None 则自动推断
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
    # 1. 估算每股自由现金流（FCF）
    ocf = to_float(fin.get("ocf_per_share", fin.get("MGJYXJJE", 0)))
    eps = to_float(fin.get("eps", fin.get("EPSJB", 0)))

    if ocf > 0:
        # 有经营现金流数据时，用 OCF × 0.7（保守扣除资本支出）
        fcf_per_share = ocf * 0.7
    elif eps > 0:
        # 回退到净利润 × 0.7
        fcf_per_share = eps * 0.7
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
