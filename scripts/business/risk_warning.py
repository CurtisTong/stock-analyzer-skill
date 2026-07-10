"""筹码显示工具（T7: 职责澄清）。

本模块仅提供筹码因子的 emoji 标识函数，不含宏观风险提示逻辑。
宏观系统性风险检测由 strategies/macro/gate.py 的 MacroSafetyGate 负责，
量化风控指标（VaR/CVaR/最大回撤）由 business/risk_metrics.py 负责。
三者职责互不重叠。
"""


def chip_emoji(score: float) -> str:
    """筹码因子 emoji 标识。

    Args:
        score: 筹码因子得分（0-100）

    Returns:
        emoji 标识
    """
    if score >= 75:
        return "🔒"  # 筹码集中（主力吸筹）
    elif score >= 50:
        return "📊"  # 正常
    else:
        return "⚠️"  # 筹码分散（主力出货）
