"""
动态风险提示：根据宏观状态生成风险提示。

与 macro gate 配合，在 /stock 和 /screener 输出中动态调整风险提示。
"""


def macro_risk_line(state: str) -> str:
    """根据宏观状态生成一行风险提示。

    Args:
        state: 宏观状态 ("GREEN" / "YELLOW" / "RED")

    Returns:
        风险提示文本，GREEN 返回空字符串
    """
    lines = {
        "GREEN": "",
        "YELLOW": "⚠️ 宏观避险情绪升温，建议仓位不超过 50%，优先防御策略",
        "RED": "🔴 系统性风险信号，建议暂停新开仓，已有持仓设好止损",
    }
    return lines.get(state, "")


def adjust_position_limit(state: str) -> float:
    """根据宏观状态调整仓位上限系数。

    Args:
        state: 宏观状态 ("GREEN" / "YELLOW" / "RED")

    Returns:
        仓位系数（1.0 = 不限制，0.5 = 半仓，0.0 = 空仓）
    """
    return {"GREEN": 1.0, "YELLOW": 0.5, "RED": 0.0}.get(state, 1.0)


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
