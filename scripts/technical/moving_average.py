"""
均线系统分析。
依赖: core (sma, stddev)
"""
import statistics

from .core import sma, stddev


_MA_PERIODS = [5, 10, 20, 60, 120, 250]


def ma_system(closes):
    """均线系统分析。返回 MA 值、排列状态、粘合度、支撑/阻力均线。"""
    result = {}
    for p in _MA_PERIODS:
        result[f"ma{p}"] = round(sma(closes, p), 2) if len(closes) >= p else None

    # 排列状态
    mas = [result[f"ma{p}"] for p in _MA_PERIODS if result[f"ma{p}"] is not None]
    if len(mas) >= 4:
        if all(mas[i] > mas[i+1] for i in range(len(mas)-1) if mas[i] and mas[i+1]):
            result["alignment"] = "多头排列"
        elif all(mas[i] < mas[i+1] for i in range(len(mas)-1) if mas[i] and mas[i+1]):
            result["alignment"] = "空头排列"
        else:
            result["alignment"] = "交叉震荡"
    else:
        result["alignment"] = "数据不足"

    # MA 粘合度 (MA5/10/20)
    short_mas = [result.get(f"ma{p}") for p in [5, 10, 20] if result.get(f"ma{p}")]
    if len(short_mas) >= 3 and statistics.mean(short_mas) > 0:
        conv = stddev(short_mas) / statistics.mean(short_mas)
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
