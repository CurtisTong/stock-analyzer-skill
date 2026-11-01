"""波动率指标（ATR）。

I9: 为缠论买卖点回踩容忍度提供动态波动率参考，
替代固定 2% 硬编码。
"""

import math


def compute_atr(highs: list, lows: list, closes: list, period: int = 14) -> float:
    """计算 ATR（Average True Range）。

    TR = max(H - L, |H - prevC|, |L - prevC|)
    ATR = TR 的简单移动平均

    Args:
        highs: 最高价序列
        lows: 最低价序列
        closes: 收盘价序列
        period: 计算周期（默认 14）

    Returns:
        ATR 值；**数据不足 period 根时返回 0**（表示 ATR 不可用），
        调用方据此回退到各自的兜底口径。

    v1.28.0 修复：此前数据不足时用**少于 period 根**的 TR 求平均并当作 ATR
    返回（实测 3 根 → 0.5），与 backtest/engine._calc_atr 的"不足则返回 0"
    口径不一致；且 atr_tolerance 文档写的"ATR 不可用时回退到收盘价 2%"
    因 ATR 从不返回 0 而**永不触发**——短历史股票的回踩容忍度被放大 2.5 倍。
    """
    n = len(closes)
    if n < 2 or period < 1:
        return 0.0

    trs = []
    for i in range(1, n):
        h = highs[i] if i < len(highs) else closes[i]
        lo = lows[i] if i < len(lows) else closes[i]
        prev_c = closes[i - 1]
        tr = max(
            h - lo,
            abs(h - prev_c),
            abs(lo - prev_c),
        )
        trs.append(tr)

    # TR 数量需达到 period 才认为 ATR 可用（与 backtest/engine._calc_atr 对齐：
    # 那边要求 len(bars) >= period + 1，即 TR 至少 period 根）
    if len(trs) < period:
        return 0.0

    return sum(trs[-period:]) / period


def atr_tolerance(
    closes: list,
    highs: list | None = None,
    lows: list | None = None,
    period: int = 14,
    k: float = 0.5,
) -> float:
    """基于 ATR 计算回踩容忍度。

    Args:
        closes: 收盘价序列
        highs: 最高价序列（可选）
        lows: 最低价序列（可选）
        period: ATR 周期
        k: ATR 乘数（默认 0.5，即半个 ATR）

    Returns:
        容忍度绝对值（价格单位），ATR 不可用时回退到收盘价 2%
    """
    if highs and lows:
        atr = compute_atr(highs, lows, closes, period)
        if atr > 0:
            return atr * k
    # 回退：收盘价的 2%
    last_close = closes[-1] if closes else 0
    return last_close * 0.02
