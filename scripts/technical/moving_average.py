"""
均线系统分析。
依赖: core (sma, stddev)
"""

from .core import sma, stddev

_MA_PERIODS = [5, 10, 20, 60, 120, 250]


def incremental_ma(closes: list, period: int) -> list:
    """增量移动平均序列，O(N) 复杂度。

    与传统逐窗口重算的 O(N*period) 相比，利用滑动窗口减去旧值加新值，
    整体仅需一次遍历。

    数据不足 period 根时返回 float('nan')，而非不准确的均值。
    NaN 语义天然安全：任何比较返回 False，运算传播 NaN，下游无需逐处写 is None 守卫。
    """
    result: list[float] = []
    window_sum = 0.0
    for i, c in enumerate(closes):
        window_sum += c
        if i >= period:
            window_sum -= closes[i - period]
            result.append(window_sum / period)
        elif i == period - 1:
            result.append(window_sum / period)
        else:
            result.append(float("nan"))
    return result


def ma_system(closes):
    """均线系统分析。返回 MA 值、排列状态、粘合度、支撑/阻力均线。"""
    result = {}
    for p in _MA_PERIODS:
        result[f"ma{p}"] = round(sma(closes, p), 2) if len(closes) >= p else None

    # 排列状态
    mas = [result[f"ma{p}"] for p in _MA_PERIODS if result[f"ma{p}"] is not None]
    if len(mas) >= 4:
        if all(
            mas[i] > mas[i + 1] for i in range(len(mas) - 1) if mas[i] and mas[i + 1]
        ):
            result["alignment"] = "多头排列"
        elif all(
            mas[i] < mas[i + 1] for i in range(len(mas) - 1) if mas[i] and mas[i + 1]
        ):
            result["alignment"] = "空头排列"
        else:
            result["alignment"] = "交叉震荡"
    else:
        result["alignment"] = "数据不足"

    # MA 粘合度 (MA5/10/20)
    short_mas = [result.get(f"ma{p}") for p in [5, 10, 20] if result.get(f"ma{p}")]
    if len(short_mas) >= 3:
        mean_val = sma(short_mas, len(short_mas))
        if mean_val and mean_val > 0:
            conv = stddev(short_mas) / mean_val
            result["convergence"] = round(conv, 4)
            if conv < 0.02:
                result["convergence_desc"] = "高度粘合(变盘窗口)"
            elif conv < 0.05:
                result["convergence_desc"] = "中度粘合"
            else:
                result["convergence_desc"] = "发散"
        else:
            result["convergence"] = None
            result["convergence_desc"] = "数据不足"
    else:
        result["convergence"] = None
        result["convergence_desc"] = "数据不足"

    # 支撑/阻力均线（相对当前价格）
    last = closes[-1] if closes else 0
    supports, resistances = [], []
    for p in _MA_PERIODS:
        v = result.get(f"ma{p}")
        if v is None:
            continue
        if v < last:
            supports.append((f"MA{p}", v))
        else:
            resistances.append((f"MA{p}", v))
    result["ma_supports"] = sorted(supports, key=lambda x: x[1], reverse=True)
    result["ma_resistances"] = sorted(resistances, key=lambda x: x[1])
    return result
