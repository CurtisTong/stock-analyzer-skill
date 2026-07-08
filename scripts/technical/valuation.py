"""估值分位计算。"""


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
        return 85.0  # 亏损股高估值风险，不应被评为"中性"
    if pe <= pe_low:
        return 15.0
    # 防御性除零：pe_mid == pe_low 时退化为中点
    if pe <= pe_mid:
        if pe_mid == pe_low:
            return 32.5  # 15 + 35/2
        return 15 + (pe - pe_low) / (pe_mid - pe_low) * 35
    # 防御性除零：pe_high == pe_mid 时退化为中点
    if pe <= pe_high:
        if pe_high == pe_mid:
            return 65.0  # 50 + 30/2
        return 50 + (pe - pe_mid) / (pe_high - pe_mid) * 30
    return min(95.0, 80 + (pe - pe_high) / pe_high * 20)
