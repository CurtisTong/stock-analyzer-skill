"""MACD 面积计算（用于背驰检测）。"""


def _macd_area(dif_series, dea_series, start_idx, end_idx, side=None):
    """计算 MACD 柱面积，用于力度对比。

    side=None: Σ|DIF - DEA|（不分色，兼容旧口径）。
    side="up": 仅累计红柱（DIF > DEA）面积——上涨笔的做多动能。
    side="down": 仅累计绿柱（DIF < DEA）面积——下跌笔的做空动能。

    分色原因：背驰比较的是同向走势的动能，若区间内柱体翻色，
    Σ|DIF-DEA| 会把反向柱也算入，混淆多空动能（如下跌笔尾端的
    反弹红柱会虚增"下跌力度"，导致漏判底背驰）。
    """
    if start_idx < 0 or end_idx >= len(dif_series) or start_idx >= end_idx:
        return 0
    area = 0
    for i in range(start_idx, end_idx + 1):
        diff = dif_series[i] - dea_series[i]
        if side == "up" and diff <= 0:
            continue
        if side == "down" and diff >= 0:
            continue
        area += abs(diff)
    return area
