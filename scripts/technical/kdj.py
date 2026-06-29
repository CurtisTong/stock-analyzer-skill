"""
KDJ 指标（含钝化检测 + 涨跌幅板差异化处理）。

2026 更新：创业板/科创板 20cm 与主板 10cm 的 KDJ 钝化阈值差异化。
20cm 股票的高波特性使其 KDJ 更容易进入超买/超卖区，钝化阈值更宽松。
"""


def kdj_full(closes, highs, lows, n=9, board="主板"):
    """KDJ 指标 + 钝化检测。

    Args:
        closes: 收盘价列表
        highs: 最高价列表
        lows: 最低价列表
        n: 周期（默认 9）
        board: 板块类型（"主板"/"创业板"/"科创板"/"北交所"），用于差异化钝化阈值

    Returns:
        dict with k/d/j/signal/钝化
    """
    if len(closes) < n + 1:
        return None

    # 确定差异化阈值
    if board in ("创业板", "科创板"):
        overbought = 85  # 20cm 股票 85 以上才算超买
        oversold = 15  # 20cm 股票 15 以下才算超卖
        dunhua_high = 85  # 20cm 高位钝化阈值（原 80）
        dunhua_low = 15  # 20cm 低位钝化阈值（原 20）
        dunhua_periods = 6  # 20cm 钝化确认周期（原 5）
    elif board == "北交所":
        overbought = 88
        oversold = 12
        dunhua_high = 88
        dunhua_low = 12
        dunhua_periods = 7  # 30cm 波动更大，需要更长的确认周期
    else:  # 主板
        overbought = 80
        oversold = 20
        dunhua_high = 80
        dunhua_low = 20
        dunhua_periods = 5

    # 计算 KDJ 序列
    k_series, d_series = [], []
    k_val, d_val = 50, 50
    for i in range(n - 1, len(closes)):
        low_n = min(lows[i - n + 1 : i + 1])
        high_n = max(highs[i - n + 1 : i + 1])
        rsv = ((closes[i] - low_n) / (high_n - low_n) * 100) if high_n != low_n else 50
        k_val = 2 / 3 * k_val + 1 / 3 * rsv
        d_val = 2 / 3 * d_val + 1 / 3 * k_val
        k_series.append(k_val)
        d_series.append(d_val)

    k_now = k_series[-1]
    d_now = d_series[-1]
    j_now = 3 * k_now - 2 * d_now

    # 金叉死叉
    kdj_signal = "正常"
    if len(k_series) >= 2:
        if k_series[-2] <= d_series[-2] and k_now > d_now:
            kdj_signal = "金叉"
        elif k_series[-2] >= d_series[-2] and k_now < d_now:
            kdj_signal = "死叉"

    # 超买超卖区（差异化阈值）
    zone = ""
    if j_now > overbought:
        zone = f"超买区(J={j_now:.0f})"
    elif j_now < oversold:
        zone = f"超卖区(J={j_now:.0f})"

    # 组合信号：金叉+超卖 或 死叉+超买
    if zone:
        if kdj_signal == "金叉" and j_now < oversold:
            kdj_signal = "金叉+超卖"
        elif kdj_signal == "死叉" and j_now > overbought:
            kdj_signal = "死叉+超买"
        elif kdj_signal == "正常":
            kdj_signal = zone

    # 钝化检测（差异化阈值和周期）
    dunhua = False
    if len(k_series) >= dunhua_periods:
        if all(k > dunhua_high for k in k_series[-dunhua_periods:]):
            dunhua = True
            kdj_signal += f" [KDJ高位钝化-趋势延续]"
        elif all(k < dunhua_low for k in k_series[-dunhua_periods:]):
            dunhua = True
            kdj_signal += f" [KDJ低位钝化-趋势延续]"

    return {
        "k": round(k_now, 2),
        "d": round(d_now, 2),
        "j": round(j_now, 2),
        "signal": kdj_signal,
        "钝化": dunhua,
        "board": board,
    }
