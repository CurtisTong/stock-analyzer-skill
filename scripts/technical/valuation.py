"""估值分位计算 + 增量 MA。"""


def pe_percentile_score(
    pe: float,
    pe_low: float = 15,
    pe_mid: float = 25,
    pe_high: float = 40,
) -> float:
    """PE 百分位估值（0-100）。

    基于固定阈值的分段映射：
      - pe <= pe_low  → 15
      - pe <= pe_mid  → 15 ~ 50 线性
      - pe <= pe_high → 50 ~ 80 线性
      - pe > pe_high  → 80 ~ 95 封顶
    """
    if pe <= 0:
        return 50.0
    if pe <= pe_low:
        return 15.0
    if pe <= pe_mid:
        return 15 + (pe - pe_low) / (pe_mid - pe_low) * 35
    if pe <= pe_high:
        return 50 + (pe - pe_mid) / (pe_high - pe_mid) * 30
    return min(95.0, 80 + (pe - pe_high) / pe_high * 20)


def incremental_ma(closes: list, period: int) -> list:
    """增量移动平均序列，O(N) 复杂度。

    与传统逐窗口重算的 O(N*period) 相比，利用滑动窗口减去旧值加新值，
    整体仅需一次遍历。
    """
    result: list[float] = []
    window_sum = 0.0
    for i, c in enumerate(closes):
        window_sum += c
        if i >= period:
            window_sum -= closes[i - period]
            result.append(window_sum / period)
        else:
            result.append(window_sum / (i + 1))
    return result
