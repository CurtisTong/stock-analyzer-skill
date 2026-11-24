"""跳空缺口识别（向上缺口 / 向下缺口 + 回补判定 + 缺口支撑阻力）。

基于相邻两根 K 线的高低点判断跳空：
- 向上缺口：今日 low > 昨日 high，缺口区间 [昨日 high, 今日 low]
- 向下缺口：今日 high < 昨日 low，缺口区间 [今日 high, 昨日 low]

纯函数、无 I/O，浮点比较统一使用 core._EPS 抑制噪声。
"""

from .core import _EPS


def detect_gaps(opens, highs, lows, closes, lookback=60):
    """检测跳空缺口。

    依据相邻两根 K 线的 high/low 判定跳空（open/close 只参与长度对齐，
    不作为跳空判据——与 A 股"跳空=高低点不重叠"的口径一致）。

    Args:
        opens: 开盘价序列。
        highs: 最高价序列。
        lows: 最低价序列。
        closes: 收盘价序列。
        lookback: 只返回"缺口形成日"落在最近 lookback 根内的缺口；
                  lookback <= 0 时返回空列表。

    Returns:
        list[dict]，每项包含：
            gap_type: 'up'（向上缺口）| 'down'（向下缺口）
            top/bottom: 缺口上下边界，恒有 top >= bottom
            width: top - bottom
            date_index: 缺口形成日（"今日"）在序列中的索引（自 1 起）
            filled: 形成后是否被后续 K 线回补
            fill_index: 首次回补的 K 线索引；未回补为 None

    回补口径（只看缺口形成日**之后**的 K 线）：
    - 向上缺口：后续 low <= top（价格跌回缺口上沿或更低）
    - 向下缺口：后续 high >= bottom（价格反弹到缺口下沿或更高）
    """
    n = min(len(opens), len(highs), len(lows), len(closes))
    if n < 2 or lookback <= 0:
        return []

    gaps = []
    for i in range(1, n):
        prev_high, prev_low = highs[i - 1], lows[i - 1]
        cur_high, cur_low = highs[i], lows[i]

        gap_type = None
        top = bottom = None
        if cur_low - prev_high > _EPS:
            # 向上跳空：今日低点高于昨日高点，缺口 = [昨高, 今低]
            gap_type = "up"
            top, bottom = cur_low, prev_high
        elif prev_low - cur_high > _EPS:
            # 向下跳空：今日高点低于昨日低点，缺口 = [今高, 昨低]
            gap_type = "down"
            top, bottom = prev_low, cur_high

        if gap_type is None:
            continue

        # 回补判定：从形成日的下一根开始，取首次满足的索引
        filled = False
        fill_index = None
        for j in range(i + 1, n):
            filled = lows[j] <= top + _EPS if gap_type == "up" else highs[j] >= bottom - _EPS
            if filled:
                fill_index = j
                break

        gaps.append(
            {
                "gap_type": gap_type,
                "top": top,
                "bottom": bottom,
                "width": top - bottom,
                "date_index": i,
                "filled": filled,
                "fill_index": fill_index,
            }
        )

    # lookback 过滤在回补判定之后：回补用完整历史，返回只截最近窗口
    start = n - lookback
    return [g for g in gaps if g["date_index"] >= start]


def gap_support_resistance(gaps, price):
    """从未回补缺口中给出最近支撑缺口与最近阻力缺口。

    方向按缺口区间 [bottom, top] 与现价的实际关系判定，**不写死 gap_type**：
    - 支撑候选：缺口整体在现价下方（top < price），取 top 最大者（最贴近现价）
    - 阻力候选：缺口整体在现价上方（bottom > price），取 bottom 最小者
    现价落在缺口区间内时两者都不是，避免同一缺口既当支撑又当阻力。

    Args:
        gaps: detect_gaps 返回的缺口列表（可含已回补项，函数内过滤）。
        price: 现价。

    Returns:
        {"nearest_gap_support": dict|None, "nearest_gap_resistance": dict|None}
    """
    empty = {"nearest_gap_support": None, "nearest_gap_resistance": None}
    if not gaps:
        return empty

    unfilled = [g for g in gaps if not g.get("filled")]
    below = [g for g in unfilled if g["top"] < price - _EPS]
    above = [g for g in unfilled if g["bottom"] > price + _EPS]

    return {
        "nearest_gap_support": max(below, key=lambda g: g["top"]) if below else None,
        "nearest_gap_resistance": min(above, key=lambda g: g["bottom"]) if above else None,
    }
