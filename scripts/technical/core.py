"""
核心数学工具和数据解析。
无内部依赖，仅使用标准库。
"""

import math
import statistics

from common import to_float

# ═══════════════════════════════════════════════════════════════
# 数学工具
# ═══════════════════════════════════════════════════════════════


# 浮点比较 epsilon，避免金叉/死叉等信号判断中的浮点噪声
_EPS = 1e-6


def sma(values, period):
    """简单移动平均。数据不足时返回 None。"""
    if len(values) < period:
        return None
    return statistics.mean(values[-period:])


def ema(values, period):
    """指数移动平均。"""
    if len(values) < period:
        return statistics.mean(values) if values else 0
    k = 2 / (period + 1)
    result = statistics.mean(values[:period])
    for v in values[period:]:
        result = v * k + result * (1 - k)
    return result


def _ema_series(values, period):
    """返回 EMA 序列（用于背离检测和 KDJ）。"""
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    result = [statistics.mean(values[:period])]
    for v in values[period:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def aligned_macd(closes, fast=12, slow=26, signal=9):
    """计算对齐的 DIF/DEA 序列，统一偏移量处理。

    解决 beichi.py / macd.py 各自计算 DIF/DEA 偏移量导致的重复和不一致。
    所有序列末尾对齐 closes 末尾（最新价），便于按索引取值。

    Returns:
        dict with:
            dif_series: DIF 序列（已对齐到 dea 时间范围）
            dea_series: DEA 序列
            dea_offset: dea_series[0] 对应的 closes 索引偏移量
    """
    if len(closes) < slow:
        return {"dif_series": [], "dea_series": [], "dea_offset": 0}

    ema_fast = _ema_series(closes, fast)
    ema_slow = _ema_series(closes, slow)
    offset = len(ema_fast) - len(ema_slow)
    dif_series = [ema_fast[offset + i] - ema_slow[i] for i in range(len(ema_slow))]
    dea_series = _ema_series(dif_series, signal)
    dea_offset = len(closes) - len(dea_series)

    # 将 dif_series 对齐到 dea_series 的时间范围
    if len(dea_series) < len(dif_series):
        dif_series = dif_series[-len(dea_series) :]

    return {
        "dif_series": dif_series,
        "dea_series": dea_series,
        "dea_offset": dea_offset,
    }


def stddev(values):
    """总体标准差。"""
    if len(values) < 2:
        return 0
    mean = statistics.mean(values)
    return math.sqrt(sum((x - mean) ** 2 for x in values) / len(values))


def _find_swing_points(values, window=5):
    """找局部极值点索引列表。用于背离检测。

    P1-14: 本方法需 window 根后续 K 线确认极值（right = values[i+1:i+window+1]），
    因此最近 window 根 K 线不会被标记为极值点。这是 by-design 的确认延迟
    （非未来数据泄露），但意味着实时信号有 window 根滞后。
    改为即时确认会降低精度（误报增加），故保持现有算法。
    """
    if len(values) < 2 * window + 1:
        return [], []
    highs, lows = [], []
    for i in range(window, len(values) - window):
        left = values[i - window : i]
        right = values[i + 1 : i + window + 1]
        if values[i] >= max(left) and values[i] > max(right):
            highs.append(i)
        if values[i] <= min(left) and values[i] < min(right):
            lows.append(i)
    return highs, lows


# ═══════════════════════════════════════════════════════════════
# 数据解析
# ═══════════════════════════════════════════════════════════════


def _parse_records(records):
    """将 K 线数据转成数值列表（统一过滤零值，保持数组对齐）。"""
    # 先过滤掉任一字段为 0 的整条记录，确保所有数组索引对齐
    valid_records = []
    for r in records:
        c = to_float(r.get("close"))
        o = to_float(r.get("open"))
        h = to_float(r.get("high"))
        lo = to_float(r.get("low"))
        v = to_float(r.get("volume"))
        if c > 0 and o > 0 and h > 0 and lo > 0 and v > 0:
            valid_records.append(r)

    closes = [to_float(r.get("close")) for r in valid_records]
    opens = [to_float(r.get("open")) for r in valid_records]
    highs = [to_float(r.get("high")) for r in valid_records]
    lows = [to_float(r.get("low")) for r in valid_records]
    volumes = [to_float(r.get("volume")) for r in valid_records]

    return closes, opens, highs, lows, volumes
