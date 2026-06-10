"""MACD 面积计算（用于背驰检测）。"""


def _macd_area(dif_series, dea_series, start_idx, end_idx):
    """计算 MACD 柱面积 = Σ|DIF - DEA|，用于力度对比。"""
    if start_idx < 0 or end_idx >= len(dif_series) or start_idx >= end_idx:
        return 0
    area = 0
    for i in range(start_idx, end_idx + 1):
        area += abs(dif_series[i] - dea_series[i])
    return area
