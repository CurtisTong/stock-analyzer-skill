"""筹码显示工具（T7: 职责澄清）。

本模块仅提供筹码因子的 emoji 标识函数，不含宏观风险提示逻辑。
宏观系统性风险检测由 strategies/macro/gate.py 的 MacroSafetyGate 负责，
量化风控指标（VaR/CVaR/最大回撤）由 business/risk_metrics.py 负责。
三者职责互不重叠。

扩展为业务指示符库,集中所有业务输出 emoji,
避免散落在多处难以维护。
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


# ---------- 业务指示符（新增）----------

# 评分等级
RATING_STRONG = "🟢"  # 强势
RATING_NEUTRAL = "🟡"  # 中性
RATING_WEAK = "🔴"  # 弱势

# 风险等级
RISK_HIGH = "🔴"  # 高风险
RISK_MID = "🟡"  # 中风险
RISK_LOW = "🟢"  # 低风险
RISK_UNKNOWN = "❓"  # 未知


def rating_emoji(
    score: float, threshold_strong: float = 75, threshold_weak: float = 50
) -> str:
    """评分等级 emoji（新增:统一 0-100 评分的语义映射）。

    Args:
        score: 评分（0-100）
        threshold_strong: 强势阈值，默认 75
        threshold_weak: 弱势阈值，默认 50（中间为中性）

    Returns:
        RATING_STRONG / RATING_NEUTRAL / RATING_WEAK
    """
    if score >= threshold_strong:
        return RATING_STRONG
    elif score <= threshold_weak:
        return RATING_WEAK
    return RATING_NEUTRAL


def trend_emoji(trend: str) -> str:
    """趋势方向 emoji（新增）。

    Args:
        trend: 趋势字符串（"上升" / "下降" / "震荡" / 其他）

    Returns:
        emoji
    """
    return {
        "上升": "📈",
        "下降": "📉",
        "震荡": "📊",
    }.get(trend, "❓")


def risk_emoji(level: str) -> str:
    """风险等级 emoji（新增）。

    Args:
        level: 风险等级字符串（"高" / "中" / "低" / "未知"）

    Returns:
        RISK_HIGH / RISK_MID / RISK_LOW / RISK_UNKNOWN
    """
    return {
        "高": RISK_HIGH,
        "中": RISK_MID,
        "低": RISK_LOW,
    }.get(level, RISK_UNKNOWN)


def volume_price_emoji(state) -> str:
    """量价状态 emoji（新增:统一成交量价信号显示）。

    Args:
        state: VP_* 枚举值或字符串描述（"放量上涨" / "缩量下跌" / ...）

    Returns:
        emoji
    """
    # 支持枚举值或字符串
    if isinstance(state, int):
        from technical.volume import (
            VP_RISE_VOL,
            VP_FALL_SHRINK,
            VP_RISE_SHRINK,
            VP_FALL_VOL,
            VP_NEUTRAL,
        )

        mapping_int = {
            VP_RISE_VOL: "💪",  # 放量上涨（强势）
            VP_FALL_SHRINK: "🛡️",  # 缩量下跌（防御）
            VP_RISE_SHRINK: "🤔",  # 缩量上涨（警惕）
            VP_FALL_VOL: "☠️",  # 放量下跌（危险）
            VP_NEUTRAL: "➖",  # 中性
        }
        return mapping_int.get(state, "❓")
    elif isinstance(state, str):
        mapping_str: dict[str, str] = {
            "放量上涨": "💪",
            "缩量下跌": "🛡️",
            "缩量上涨": "🤔",
            "放量下跌": "☠️",
            "量价中性": "➖",
            "配合": "💪",
            "背离": "🤔",
        }
        return mapping_str.get(state, "❓")
    return "❓"
