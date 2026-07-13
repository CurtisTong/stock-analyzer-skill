"""DCF（折现现金流）简易估值模型。

两阶段 DCF：
- 阶段 1（1-5 年）：高增长期，使用分析师预期增速或历史增速
- 阶段 2（6-10 年）：过渡期，增速逐年递减至永续增长率

输出：内在价值 vs 市价的偏离度（正数 = 低估，负数 = 高估）。

注意：A 股 FCF 数据不完整，本模型使用以下近似：
- FCF = 经营现金流 - 资本支出（如有）
- 回退到 净利润 × 0.7（保守估计）

v2.7.1: 支持 beta 驱动 WACC（CAPM）。传入 stock_code 时用真实 beta + 宏观利率
计算动态折现率，替代 v2.4.0 的硬编码 7 行业字典。
"""

from common import to_float

# v2.7.1: CAPM WACC 计算的合理区间约束
_WACC_MIN = 0.06  # 6% 下限（极低 beta + 低利率也不应低于此）
_WACC_MAX = 0.20  # 20% 上限（极高 beta 也不应超过此，避免 DCF 失真）
_RISK_FREE_FALLBACK = 0.025  # 10Y 国债 fallback（2.5%）
_ERP_FALLBACK = 0.055  # 沪深 300 ERP fallback（5.5%）


def _compute_capm_wacc(stock_code: str) -> tuple[float, str] | None:
    """用 CAPM 计算动态 WACC（v2.7.1 新增）。

    WACC = risk_free_rate + beta × equity_risk_premium

    数据来源：
    - beta: industry_beta.compute_beta()（60 日 OLS，动态选基准）
    - risk_free_rate: macro_snapshot.json 的 treasury_10y_pct
    - ERP: macro_snapshot.json 的 erp_sh300_pct

    Args:
        stock_code: 个股代码（如 sh600519）

    Returns:
        (wacc, source_label) 元组，失败返回 None。
        wacc 已约束在 [_WACC_MIN, _WACC_MAX] 区间。
    """
    try:
        import sys
        from pathlib import Path

        # 确保 scripts/ 在 import 路径
        scripts_dir = Path(__file__).resolve().parent.parent.parent
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        from industry_beta import compute_beta
        from macro_indicators import fetch_treasury_10y, fetch_erp_sh300

        # 1. 拉真实 beta（60 日 OLS + 动态选基准）
        beta_result = compute_beta(stock_code)
        if not beta_result or beta_result.get("beta") is None:
            return None
        beta = beta_result["beta"]

        # 2. 拉无风险利率（10Y 国债）
        treasury = fetch_treasury_10y()
        risk_free = (treasury["value"] / 100) if treasury else _RISK_FREE_FALLBACK

        # 3. 拉 ERP（沪深 300 风险溢价）
        erp_data = fetch_erp_sh300()
        erp = (erp_data["value"] / 100) if erp_data else _ERP_FALLBACK

        # 4. CAPM
        wacc = risk_free + beta * erp

        # 5. 合理区间约束
        wacc = max(_WACC_MIN, min(_WACC_MAX, wacc))

        return (
            round(wacc, 4),
            f"CAPM(beta={beta:.2f}, rf={risk_free:.3f}, erp={erp:.3f})",
        )
    except Exception:
        return None


def _fallback_industry_discount(industry: str) -> tuple[float, str]:
    """v2.4.0 硬编码行业字典 fallback（CAPM 不可用时使用）。

    Returns:
        (discount_rate, source_label)
    """
    _DISCOUNT_RATES = {
        "科技": 0.12,
        "周期": 0.11,
        "医药": 0.10,
        "重资产": 0.10,
        "默认": 0.10,
        "金融": 0.09,
        "消费": 0.09,
    }
    rate = _DISCOUNT_RATES.get(industry, _DISCOUNT_RATES["默认"])
    return (rate, f"行业字典({industry}={rate:.0%})")


def dcf_valuation(
    price: float,
    fin: dict,
    growth_rate: float = None,
    discount_rate: float = 0.10,
    terminal_growth: float = 0.03,
    years_high: int = 5,
    years_transition: int = 5,
    industry: str = "默认",
    stock_code: str = None,
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
        stock_code: v2.7.1 新增。传入时用 CAPM 动态计算 WACC（真实 beta + 宏观利率），
            替代硬编码行业字典。失败时回退到行业字典。

    Returns:
        {
            "intrinsic_value": 内在价值,
            "price": 当前价,
            "margin_of_safety": 安全边际（正数=低估）,
            "fcf_per_share": 每股自由现金流,
            "growth_rate": 使用的增长率,
            "discount_rate": 使用的折现率,
            "wacc_source": "CAPM" | "行业字典" | "用户传入",
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

    # v2.7.1: 折现率三级优先级
    # 1. 用户显式传入（discount_rate != 0.10）-> "用户传入"
    # 2. stock_code 传入 -> CAPM 动态 WACC -> "CAPM"
    # 3. 回退 -> 行业字典 -> "行业字典"
    wacc_source = "用户传入"
    if discount_rate == 0.10:
        # 默认值，尝试 CAPM
        if stock_code:
            capm_result = _compute_capm_wacc(stock_code)
            if capm_result is not None:
                discount_rate = capm_result[0]
                wacc_source = capm_result[1]
            else:
                # CAPM 失败，回退行业字典
                discount_rate, wacc_source = _fallback_industry_discount(industry)
        else:
            # 未传 stock_code，直接用行业字典
            discount_rate, wacc_source = _fallback_industry_discount(industry)

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
        # 用单期净利同比增速（FinanceRecord 暂无 3 年 CAGR 字段）
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
        "wacc_source": wacc_source,
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
# DCF 三情景估值（v2.5.0 Phase 3）
# ═══════════════════════════════════════════════════════════════

# 周期位置 -> 三情景权重（bear/base/bull）
_CYCLE_SCENARIO_WEIGHTS = {
    "high": {"bear": 0.80, "base": 0.15, "bull": 0.05},  # 疑似顶部：悲观主导
    "mid": {"bear": 0.25, "base": 0.50, "bull": 0.25},  # 中性：均衡
    "low": {"bear": 0.05, "base": 0.15, "bull": 0.80},  # 疑似底部：乐观主导
    "unknown": {"bear": 0.25, "base": 0.50, "bull": 0.25},  # 未知：同中性
}


def dcf_scenario_valuation(
    price: float,
    fin: dict,
    industry: str = "默认",
    cycle_position: str = "unknown",
    stock_code: str = None,
) -> dict:
    """三情景 DCF 估值（v2.5.0 Phase 3）。

    基于周期位置评估矩阵，设定悲观/中性/乐观三种情景下的增长率，
    各跑一次 DCF 后按周期位置赋权合成安全边际。

    替代原"5年平均法无法计算归零"的僵化逻辑：
    - 不再因无法取得确定数字而归零
    - 而是用情景加权量化"安全边际很薄但有"
    - 周期高位时悲观情景权重 80%，如仍有正向安全边际则清晰量化

    Args:
        price: 当前股价
        fin: 财务 dict
        industry: 行业类型
        cycle_position: 周期位置 "high"/"mid"/"low"/"unknown"
        stock_code: 传入时用 CAPM 计算 WACC

    Returns:
        {
            "intrinsic_value": 加权内在价值,
            "margin_of_safety": 加权安全边际,
            "scenarios": {bear/base/bull: {intrinsic_value, margin_of_safety}},
            "scenario_weights": {bear/base/bull: weight},
            "cycle_position": cycle_position,
            "method": "dcf_scenario",
        }
    """
    # 三情景增长率推断
    profit_yoy = to_float(
        fin.get("net_profit_yoy", fin.get("PARENTNETPROFITTZ", 0))
    )
    current_growth = min(max(profit_yoy / 100, 0.01), 0.30) if profit_yoy > 0 else 0.05

    # bear: 周期底部利润（增速大幅下滑甚至负增长）
    bear_growth = max(0.01, current_growth * 0.2)
    # base: 正常化利润（增速回归均值）
    base_growth = max(0.03, min(current_growth * 0.5, 0.15))
    # bull: 当前利润（维持当前增速）
    bull_growth = current_growth

    scenarios = {}
    for name, growth in [("bear", bear_growth), ("base", base_growth), ("bull", bull_growth)]:
        result = dcf_valuation(
            price, fin, growth_rate=growth, industry=industry, stock_code=stock_code
        )
        if result.get("error"):
            # 单情景无数据时返回中性
            return {
                "intrinsic_value": 0,
                "price": price,
                "margin_of_safety": -100,
                "error": result["error"],
                "method": "dcf_scenario",
            }
        scenarios[name] = {
            "intrinsic_value": result["intrinsic_value"],
            "margin_of_safety": result["margin_of_safety"],
            "growth_rate": growth,
        }

    # 按周期位置赋权
    weights = _CYCLE_SCENARIO_WEIGHTS.get(cycle_position, _CYCLE_SCENARIO_WEIGHTS["unknown"])

    # 加权合成安全边际
    weighted_margin = sum(
        scenarios[s]["margin_of_safety"] * weights[s] for s in ("bear", "base", "bull")
    )
    weighted_value = sum(
        scenarios[s]["intrinsic_value"] * weights[s] for s in ("bear", "base", "bull")
    )

    return {
        "intrinsic_value": round(weighted_value, 2),
        "price": price,
        "margin_of_safety": round(weighted_margin, 1),
        "scenarios": scenarios,
        "scenario_weights": weights,
        "cycle_position": cycle_position,
        "method": "dcf_scenario",
    }


def dcf_scenario_score(
    price: float,
    fin: dict,
    industry: str = "默认",
    cycle_position: str = "unknown",
) -> float:
    """三情景 DCF 评分（0-100，50=合理估值）。

    v2.5.0 Phase 3：用三情景加权安全边际替代单点估计。
    周期股在疑似高位时悲观情景权重 80%，如仍有正向安全边际，
    就能清晰量化"安全边际很薄但有"，而非粗暴归零。
    """
    result = dcf_scenario_valuation(price, fin, industry, cycle_position)
    margin = result.get("margin_of_safety", -100)

    if result.get("error"):
        return 50  # 无数据给中性分（非零）

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
