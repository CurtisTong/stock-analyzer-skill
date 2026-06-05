"""
KDJ 指标（含钝化检测）。
无内部依赖。
"""


def kdj_full(closes, highs, lows, n=9):
    """KDJ 指标 + 钝化检测。"""
    if len(closes) < n + 1:
        return None

    # 计算 KDJ 序列
    k_series, d_series = [], []
    k_val, d_val = 50, 50
    for i in range(n - 1, len(closes)):
        low_n = min(lows[i - n + 1:i + 1])
        high_n = max(highs[i - n + 1:i + 1])
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

    # 超买超卖区
    if j_now > 100:
        kdj_signal = f"超买区(J={j_now:.0f})"
    elif j_now < 0:
        kdj_signal = f"超卖区(J={j_now:.0f})"

    # A 股特化：KDJ 钝化检测
    dunhua = False
    if len(k_series) >= 5:
        if all(k > 80 for k in k_series[-5:]):
            dunhua = True
            kdj_signal += " [KDJ高位钝化-趋势延续]"
        elif all(k < 20 for k in k_series[-5:]):
            dunhua = True
            kdj_signal += " [KDJ低位钝化-趋势延续]"

    return {
        "k": round(k_now, 2),
        "d": round(d_now, 2),
        "j": round(j_now, 2),
        "signal": kdj_signal,
        "钝化": dunhua,
    }
