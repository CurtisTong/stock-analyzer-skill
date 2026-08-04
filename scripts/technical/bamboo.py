"""竹节法卖点识别（逐日高低价阶梯对比）。

策略逻辑：
- 今天和昨天相比，最高价不再新高 -> 走弱，减仓信号
- 今天和昨天相比，最低价更低 -> 转势，清仓信号

用回看窗口内的最高价/最低价作为"新高/新低"基准，
而非仅与前一日对比，以过滤单日毛刺噪声。

依赖: core (_EPS)
"""

from .core import _EPS

_BAMBOO_WINDOW = 5  # 回看窗口，判断"新高/新低"的基准


def bamboo_node(highs, lows, closes, window=_BAMBOO_WINDOW):
    """竹节法：逐日对比高低价阶梯。

    Args:
        highs: 最高价序列 list[float]
        lows: 最低价序列 list[float]
        closes: 收盘价序列 list[float]（预留，当前未使用）
        window: 回看窗口，默认 5 日

    Returns:
        dict: {"status": str, "signal": int, "desc": str,
               "prev_high": float, "prev_low": float, "today_high": float, "today_low": float}
        signal: -2=转势(清仓), -1=走弱(减仓), 0=维持
        数据不足时返回 None。
    """
    if len(highs) < window + 1 or len(lows) < window + 1:
        return None

    # 前 window 日（不含今日）的最高价/最低价
    prev_highs = highs[-(window + 1) : -1]
    prev_lows = lows[-(window + 1) : -1]
    prev_high = max(prev_highs)
    prev_low = min(prev_lows)

    today_high = highs[-1]
    today_low = lows[-1]

    # 转势优先级高于走弱：最低价创新低 -> 清仓
    if today_low < prev_low - _EPS:
        return {
            "status": "竹节转势(最低价创新低)",
            "signal": -2,
            "desc": f"今日最低{today_low:.2f}跌破前{window}日最低{prev_low:.2f}，转势清仓",
            "prev_high": round(prev_high, 2),
            "prev_low": round(prev_low, 2),
            "today_high": round(today_high, 2),
            "today_low": round(today_low, 2),
        }

    # 走弱：最高价未创新高 -> 减仓
    if today_high <= prev_high + _EPS:
        return {
            "status": "竹节走弱(最高价未创新高)",
            "signal": -1,
            "desc": f"今日最高{today_high:.2f}未超前{window}日最高{prev_high:.2f}，走弱减仓",
            "prev_high": round(prev_high, 2),
            "prev_low": round(prev_low, 2),
            "today_high": round(today_high, 2),
            "today_low": round(today_low, 2),
        }

    # 维持：高低阶梯抬升
    return {
        "status": "竹节维持(高低阶梯抬升)",
        "signal": 0,
        "desc": f"今日最高{today_high:.2f}>前{window}日高{prev_high:.2f}，最低{today_low:.2f}>前{window}日低{prev_low:.2f}，趋势维持",
        "prev_high": round(prev_high, 2),
        "prev_low": round(prev_low, 2),
        "today_high": round(today_high, 2),
        "today_low": round(today_low, 2),
    }
