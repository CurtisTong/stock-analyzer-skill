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


def sma(values, period):
    """简单移动平均。"""
    if len(values) < period:
        return statistics.mean(values) if values else 0
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


def stddev(values):
    """总体标准差。"""
    if len(values) < 2:
        return 0
    mean = statistics.mean(values)
    return math.sqrt(sum((x - mean) ** 2 for x in values) / len(values))


def _find_swing_points(values, window=5):
    """找局部极值点索引列表。用于背离检测。"""
    if len(values) < 2 * window + 1:
        return [], []
    highs, lows = [], []
    for i in range(window, len(values) - window):
        left = values[i - window:i]
        right = values[i + 1:i + window + 1]
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
