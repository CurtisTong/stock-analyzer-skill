"""分析师预期因子评分：一致预期净利润上调/下调、目标价隐含空间。

2026 新增：将分析师预期纳入多因子选股管道。
分析师一致预期的变化是 A 股重要的 alpha 信号。

注意：当前实现基于可用数据源，部分维度可能需要扩展。
"""

from common import to_float, clamp


def analyst_expectation_score(quote: dict, fin: dict, industry: str = "默认") -> float:
    """分析师预期因子评分。满分 100（中性 50）。

    维度：
    - 目标价隐含空间（0~+25）：当前价低于目标价时加分
    - 净利润预期变化（-15~+15）：预期上调加分，下调扣分
    - 研报覆盖度（0~+10）：有覆盖加分，无覆盖中性

    Args:
        quote: 行情 dict（含 price, target_price 等）
        fin: 财务 dict（含 analyst_consensus 等）
        industry: 行业名称

    Returns:
        0-100 分析师预期因子得分（50=中性）
    """
    score = 50.0  # 基准分

    # 1. 目标价隐含空间（0~+25）
    price = to_float(quote.get("price", 0))
    target_price = to_float(fin.get("target_price", fin.get("ANALYST_TARGET_PRICE", 0)))
    if price > 0 and target_price > 0:
        upside = (target_price - price) / price * 100
        if upside > 30:
            score += 25  # 大幅上行空间
        elif upside > 15:
            score += 18
        elif upside > 5:
            score += 10
        elif upside < -20:
            score -= 15  # 目标价低于现价
        elif upside < -10:
            score -= 8

    # 2. 净利润预期变化（-15~+15）
    # 用净利增速的变化方向作为 proxy
    profit_yoy = to_float(fin.get("net_profit_yoy", fin.get("PARENTNETPROFITTZ", 0)))
    revenue_yoy = to_float(fin.get("revenue_yoy", fin.get("TOTALOPERATEREVETZ", 0)))

    if profit_yoy > 50 and revenue_yoy > 20:
        score += 15  # 高增长 + 营收配合
    elif profit_yoy > 30:
        score += 10
    elif profit_yoy > 10:
        score += 5
    elif profit_yoy < -30:
        score -= 15  # 大幅下滑
    elif profit_yoy < -10:
        score -= 8

    # 3. 研报覆盖度（0~+10）
    # 用机构持仓作为 proxy（有机构关注的股票通常有研报覆盖）
    inst_count = to_float(fin.get("institution_count", fin.get("HOLD_ORG_NUM", 0)))
    if inst_count > 20:
        score += 10  # 大量机构覆盖
    elif inst_count > 5:
        score += 5
    # 无覆盖不扣分

    return clamp(score)
