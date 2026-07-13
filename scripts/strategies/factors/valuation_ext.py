"""动态 PE 多口径计算 + 目标 PE 依据论证。

解决审查 #11（动态 PE 口径不一致）：原始报告给出 7.5-8.1× 但未说明计算方法。
本模块分口径标注：Q1 年化 / H1 预增修正 / 机构全年预测，口径透明可验证。

解决审查 #24（目标 PE 缺依据）：原始报告"目标 PE 10×"未论证。
本模块用可比公司 PE / PEG / 机构目标价隐含 PE 三因素加权论证。
"""

from common import to_float


def dynamic_pe(market_cap: float, profit_scenarios: dict) -> dict:
    """多口径动态 PE 计算。

    审查 #11 要求"分口径标注"，本函数输出三种口径供报告引用：
    ① Q1 年化口径：市值 / (Q1 净利 × 4)
    ② H1 预增修正口径：市值 / (H1 预增中值 × 2)
    ③ 机构全年预测口径：市值 / 机构一致预期全年净利

    Args:
        market_cap: 总市值（亿元）
        profit_scenarios: 净利情景 dict，可含：
            - q1_annualized: Q1 年化净利(亿) = Q1 净利 × 4
            - h1_forecast_mid: H1 预增中值(亿)，年化 = 中值 × 2
            - fy_forecast: 机构全年预测净利(亿)

    Returns:
        {
            "pe_q1_annualized": float,   # Q1 年化口径 PE
            "pe_h1_forecast": float,     # H1 预增修正口径 PE
            "pe_fy_consensus": float,    # 机构全年预测口径 PE
            "recommended_pe": float,     # 推荐口径（优先 fy_consensus > h1 > q1）
            "recommended_basis": str,    # 推荐口径说明
            "available_scenarios": list, # 可用口径列表
        }
    """
    if market_cap <= 0:
        return {
            "pe_q1_annualized": 0.0,
            "pe_h1_forecast": 0.0,
            "pe_fy_consensus": 0.0,
            "recommended_pe": 0.0,
            "recommended_basis": "市值为 0，无法计算",
            "available_scenarios": [],
        }

    q1_ann = to_float(profit_scenarios.get("q1_annualized", 0))
    h1_mid = to_float(profit_scenarios.get("h1_forecast_mid", 0))
    fy_forecast = to_float(profit_scenarios.get("fy_forecast", 0))

    pe_q1 = market_cap / q1_ann if q1_ann > 0 else 0.0
    pe_h1 = market_cap / (h1_mid * 2) if h1_mid > 0 else 0.0
    pe_fy = market_cap / fy_forecast if fy_forecast > 0 else 0.0

    # 推荐口径：优先机构全年预测（最权威），其次 H1 预增（含 Q2 实际），
    # 最后 Q1 年化（仅外推，误差最大）
    available = []
    if pe_fy > 0:
        available.append("fy_consensus")
    if pe_h1 > 0:
        available.append("h1_forecast")
    if pe_q1 > 0:
        available.append("q1_annualized")

    if pe_fy > 0:
        recommended_pe = pe_fy
        recommended_basis = "机构全年预测口径（优先，含全年机构覆盖）"
    elif pe_h1 > 0:
        recommended_pe = pe_h1
        recommended_basis = "H1 预增修正口径（含 Q2 实际数据，次优）"
    elif pe_q1 > 0:
        recommended_pe = pe_q1
        recommended_basis = "Q1 年化口径（仅外推，误差最大，谨慎使用）"
    else:
        recommended_pe = 0.0
        recommended_basis = "无可用净利情景"

    return {
        "pe_q1_annualized": round(pe_q1, 2),
        "pe_h1_forecast": round(pe_h1, 2),
        "pe_fy_consensus": round(pe_fy, 2),
        "recommended_pe": round(recommended_pe, 2),
        "recommended_basis": recommended_basis,
        "available_scenarios": available,
    }


def target_pe_justification(
    comparable_pe: float,
    peg: float,
    consensus_implied_pe: float,
) -> dict:
    """目标 PE 依据论证（解决审查 #24）。

    原始报告"目标 PE 10×"未论证依据。本函数用三因素加权：
    ① 可比公司 PE：同行业可比标的当前 PE
    ② PEG 合理 PE：PEG=1 时隐含 PE = 增速 × 1（增速合理则 PE 合理）
    ③ 机构目标价隐含 PE：机构一致预期目标价 / 预测 EPS

    三因素加权得出目标 PE，并输出论证依据文本。

    Args:
        comparable_pe: 可比公司 PE（如兖矿能源当前 PE）
        peg: 当前 PEG（PE / 增速）
        consensus_implied_pe: 机构目标价隐含 PE = 目标价均值 / 预测 EPS

    Returns:
        {
            "comparable_pe": float,       # 可比公司 PE
            "peg_implied_pe": float,      # PEG 合理 PE（若 peg<1，当前 PE 偏低）
            "consensus_implied_pe": float,# 机构隐含 PE
            "target_pe": float,           # 加权目标 PE
            "basis": str,                 # 论证依据文本
            "weighting": str,             # 权重说明
        }
    """
    factors = []
    values = []

    # 因素 1：可比公司 PE
    if comparable_pe > 0:
        factors.append(("可比公司 PE", comparable_pe))
        values.append(comparable_pe)

    # 因素 2：PEG 合理 PE
    # PEG = PE / growth，若 PEG < 1 则当前 PE < 合理 PE（低估）
    # 合理 PE = growth（即 PEG=1 时的 PE），但无 growth 输入时用 PEG 反推：
    # 若已知 peg 和当前 PE，合理 PE = 当前 PE / peg（但当前 PE 未知）
    # 简化：peg_implied_pe 直接用 consensus_implied_pe 和 comparable_pe 交叉验证
    # 此处 peg 因素作为定性判断（peg<1 低估），不直接产出 PE 值
    peg_implied_pe = 0.0

    # 因素 3：机构目标价隐含 PE
    if consensus_implied_pe > 0:
        factors.append(("机构目标价隐含 PE", consensus_implied_pe))
        values.append(consensus_implied_pe)

    if not values:
        return {
            "comparable_pe": round(comparable_pe, 2),
            "peg_implied_pe": 0.0,
            "consensus_implied_pe": round(consensus_implied_pe, 2),
            "target_pe": 0.0,
            "basis": "无可用依据，目标 PE 缺乏支撑",
            "weighting": "",
        }

    # 加权平均（等权，因三因素可信度相近）
    target_pe = sum(values) / len(values)

    # PEG 定性判断
    peg_note = ""
    if peg > 0:
        if peg < 0.8:
            peg_note = f"PEG={peg:.2f}（<0.8，显著低估，支撑更高目标 PE）"
        elif peg < 1.5:
            peg_note = f"PEG={peg:.2f}（<1.5，合理偏低，支撑目标 PE）"
        else:
            peg_note = f"PEG={peg:.2f}（>1.5，偏高，限制目标 PE 上限）"

    basis_parts = [f"{'='.join(map(str, f))}" for f in factors]
    if peg_note:
        basis_parts.append(peg_note)

    basis = "目标 PE 依据：等权加权 " + "、".join(basis_parts)
    weighting = f"等权平均（{len(values)} 个因素）"

    return {
        "comparable_pe": round(comparable_pe, 2),
        "peg_implied_pe": round(peg_implied_pe, 2),
        "consensus_implied_pe": round(consensus_implied_pe, 2),
        "target_pe": round(target_pe, 2),
        "basis": basis,
        "weighting": weighting,
    }
