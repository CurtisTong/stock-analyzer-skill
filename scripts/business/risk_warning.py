"""筹码因子 emoji 标识。

P1-20: 删除 macro_risk_line / adjust_position_limit 死代码（零调用）。
原始设计为"与 macro gate 配合在 /stock 和 /screener 输出中动态调整风险提示"，
但该集成从未实现。chip_emoji 被 screener.py 使用，保留。
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
