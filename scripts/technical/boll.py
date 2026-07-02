"""
布林带分析。
依赖: core (sma, stddev)
"""

from .core import sma, stddev


def bollinger(closes, period=20, multiplier=2.0):
    """布林带分析：上/中/下轨 + 带宽 + 价格位置。"""
    if len(closes) < period:
        return None

    mid = sma(closes, period)
    sd = stddev(closes[-period:])
    upper = mid + multiplier * sd
    lower = mid - multiplier * sd
    bandwidth = (upper - lower) / mid if mid > 0 else 0
    last = closes[-1]
    position = (last - lower) / (upper - lower) if (upper - lower) > 1e-6 else 0.5

    # 带宽状态
    if bandwidth < 0.05:
        bw_desc = "极度收窄(变盘信号)"
    elif bandwidth < 0.10:
        bw_desc = "收窄中"
    else:
        bw_desc = "正常带宽"

    # 价格位置
    if position > 0.9:
        pos_desc = "触及上轨"
    elif position < 0.1:
        pos_desc = "触及下轨"
    elif position > 0.7:
        pos_desc = "偏上轨"
    elif position < 0.3:
        pos_desc = "偏下轨"
    else:
        pos_desc = "中轨附近"

    return {
        "upper": round(upper, 2),
        "mid": round(mid, 2),
        "lower": round(lower, 2),
        "bandwidth": round(bandwidth, 4),
        "bandwidth_desc": bw_desc,
        "position": round(position, 3),
        "position_desc": pos_desc,
    }
