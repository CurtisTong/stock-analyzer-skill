"""成本分布（筹码分布）计算。

模型：三角分布 + 换手衰减
- 流通筹码总量固定为 100%；
- 每日换手率 r = 当日成交量 ÷ 流通股本；
- 旧筹码按 (1 - r) 衰减，新增的 r 按当日 [low, high] 区间三角分布铺开，
  峰值取当日均价 (high + low + close) / 3。

输出获利盘/套牢盘比例、平均成本、主密集区、收复密集区所需反弹幅度，
用于判断上方解套抛压（"反弹的第一道墙是密集区，不是均线"）。

注意：结果为**模型推算值**，非交易所观测数据；不同软件的衰减参数不同，
横向比较须使用同一口径。
"""

from typing import Any

from common import to_float

_DEFAULT_BINS = 240
_DEFAULT_WINDOW = 250
_MIN_BARS = 20  # 少于该根数不计算，避免样本过短的伪分布
_MIN_PEAK_MASS = 1.0  # 最近上方压力的最小占比（%），过滤噪声峰
_HALF_HEIGHT = 0.5  # 密集区半高宽阈值（相对峰值）
_WALL_MASS_PCT = 25.0  # 密集区占流通盘 ≥ 该值视为"墙厚"
_TIER_DEEP_PROFIT = 3.0  # 获利盘 ≤ 该值 -> 深度套牢
_TIER_FOOT_PROFIT = 15.0  # 获利盘 ≥ 该值 -> 筹码在脚下
_TIER_DEEP_REBOUND = 15.0  # 需反弹 ≥ 该值 -> 深度套牢


def _as_dict(r: Any) -> dict:
    """把 K 线记录（dict 或 KlineBar 等对象）统一成 dict。"""
    if isinstance(r, dict):
        return r
    to_dict = getattr(r, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    return {k: getattr(r, k, None) for k in ("day", "open", "high", "low", "close", "volume")}


def _valid_bars(records: Any) -> list[dict]:
    """过滤零值/缺字段记录，保证 OHLCV 完整。"""
    bars = []
    for r in records or []:
        b = _as_dict(r)
        if (
            to_float(b.get("high")) > 0
            and to_float(b.get("low")) > 0
            and to_float(b.get("close")) > 0
            and to_float(b.get("volume")) > 0
        ):
            bars.append(b)
    return bars


def _accumulate(bars: list[dict], float_shares: float, bins: int) -> tuple[list[float], list[float]]:
    """逐日累积筹码分布，返回 (价格网格中心, 各档筹码占比%)。"""
    lo = min(to_float(b.get("low")) for b in bars)
    hi = max(to_float(b.get("high")) for b in bars)
    if hi <= lo:
        hi = lo * 1.01 + 1e-6
    step = (hi - lo) / bins
    centers = [lo + step * (i + 0.5) for i in range(bins)]
    chips = [0.0] * bins

    for b in bars:
        turnover = min(to_float(b.get("volume")) / float_shares, 1.0)
        if turnover <= 0:
            continue
        # 旧筹码衰减
        for i in range(bins):
            chips[i] *= 1.0 - turnover
        # 新增筹码按三角分布铺开
        low = to_float(b.get("low"))
        high = to_float(b.get("high"))
        if high <= low:
            high = low + step
        avg = (high + low + to_float(b.get("close"))) / 3.0
        weights = []
        total = 0.0
        for c in centers:
            if c < low or c > high:
                weights.append(0.0)
                continue
            if c <= avg and avg > low:
                w = (c - low) / (avg - low)
            elif c > avg and high > avg:
                w = (high - c) / (high - avg)
            else:
                w = 1.0
            weights.append(w)
            total += w
        if total <= 0:
            continue
        for i in range(bins):
            chips[i] += turnover * weights[i] / total

    s = sum(chips)
    if s <= 0:
        return centers, chips
    return centers, [c / s * 100.0 for c in chips]


def _cost_range(chips: list[float], centers: list[float], low_pct: float, high_pct: float) -> tuple[float, float]:
    """取累计占比达到 [low_pct, high_pct] 的成本区间。"""
    acc = 0.0
    lo_v = centers[0]
    hi_v = centers[-1]
    lo_done = False
    for c, x in zip(chips, centers):
        acc += c
        if not lo_done and acc >= low_pct:
            lo_v = x
            lo_done = True
        if acc >= high_pct:
            hi_v = x
            break
    return lo_v, hi_v


def _peaks(chips: list[float], centers: list[float]) -> list[tuple[float, float, int]]:
    """局部极大值峰，返回 [(占比, 价格, 索引)] 按占比降序。"""
    peaks = []
    for i in range(1, len(chips) - 1):
        if chips[i] >= chips[i - 1] and chips[i] >= chips[i + 1]:
            peaks.append((chips[i], centers[i], i))
    peaks.sort(reverse=True)
    return peaks


def _band(chips: list[float], centers: list[float], peak_idx: int, peak_mass: float) -> tuple[float, float, float]:
    """以峰为中心向两侧扩展到半高宽，返回 (下界, 上界, 区间占比)。"""
    left = right = peak_idx
    threshold = peak_mass * _HALF_HEIGHT
    while left > 0 and chips[left - 1] > threshold:
        left -= 1
    while right < len(chips) - 1 and chips[right + 1] > threshold:
        right += 1
    return centers[left], centers[right], sum(chips[left : right + 1])


def classify_tier(profit_ratio: float, contains_price: bool, rebound_to_main_pct: float | None) -> str:
    """按筹码结构分档。

    阈值以初始样本（7 只持仓 + 中际旭创）标定，**未经校准**，后续按实际分布调整。
    """
    if contains_price or profit_ratio >= _TIER_FOOT_PROFIT:
        return "筹码在脚下"
    if profit_ratio <= _TIER_DEEP_PROFIT or (
        rebound_to_main_pct is not None and rebound_to_main_pct >= _TIER_DEEP_REBOUND
    ):
        return "深度套牢"
    return "上方有墙"


def chip_distribution(
    records: Any,
    float_shares: float,
    price: float | None = None,
    bins: int = _DEFAULT_BINS,
    window: int = _DEFAULT_WINDOW,
) -> dict | None:
    """计算成本分布（筹码分布）。

    Args:
        records: K 线记录列表（dict 或含 to_dict() 的对象），需含 high/low/close/volume
        float_shares: 流通股本（股）
        price: 现价，缺省取最后一根收盘价
        bins: 价格分档数
        window: 回看窗口（交易日）

    Returns:
        成本分布 dict；数据不足或流通股本非法时返回 None。
    """
    bars = _valid_bars(records)[-window:]
    if len(bars) < _MIN_BARS:
        return None
    fs = to_float(float_shares)
    if fs <= 0:
        return None
    px = to_float(price) if price else to_float(bars[-1].get("close"))
    if px <= 0:
        return None

    centers, chips = _accumulate(bars, fs, bins)
    total = sum(chips)
    if total <= 0:
        return None

    profit = sum(c for c, x in zip(chips, centers) if x <= px)
    avg_cost = sum(c * x for c, x in zip(chips, centers)) / total
    lo90, hi90 = _cost_range(chips, centers, 5.0, 95.0)

    peaks = _peaks(chips, centers)
    overhead = [p for p in peaks if p[1] > px]
    main = None
    if overhead:
        pk_mass, pk_price, pk_idx = overhead[0]
        band_lo, band_hi, band_mass = _band(chips, centers, pk_idx, pk_mass)
        main = {
            "peak": round(pk_price, 3),
            "band": [round(band_lo, 3), round(band_hi, 3)],
            "mass_pct": round(band_mass, 1),
            "contains_price": band_lo <= px <= band_hi,
        }

    nearest = None
    for price_v, mass in sorted(((centers[i], chips[i]) for i in range(len(centers)) if centers[i] > px)):
        if mass >= _MIN_PEAK_MASS:
            nearest = {
                "price": round(price_v, 3),
                "mass_pct": round(mass, 2),
                "rebound_pct": round((price_v / px - 1) * 100, 1),
            }
            break

    rebound = round((main["peak"] / px - 1) * 100, 1) if main else None
    profit_ratio = round(profit / total * 100, 1)
    contains = bool(main and main["contains_price"])
    wall_value = round(main["mass_pct"] / 100 * fs * main["peak"] / 1e8, 1) if main else None

    return {
        "price": round(px, 3),
        "float_shares": fs,
        "bars": len(bars),
        "window_start": bars[0].get("day") or bars[0].get("date"),
        "window_end": bars[-1].get("day") or bars[-1].get("date"),
        "turnover_window_pct": round(sum(min(to_float(b.get("volume")) / fs, 1.0) for b in bars) * 100, 1),
        "avg_cost": round(avg_cost, 3),
        "price_vs_avg_cost_pct": round((px / avg_cost - 1) * 100, 1) if avg_cost > 0 else None,
        "profit_ratio": profit_ratio,
        "trapped_ratio": round(100.0 - profit_ratio, 1),
        "cost_range_90": {"low": round(lo90, 3), "high": round(hi90, 3)},
        "main_cluster": main,
        "rebound_to_main_pct": rebound,
        "nearest_overhead": nearest,
        "wall_value_yi": wall_value,
        "wall_thick": bool(main and main["mass_pct"] >= _WALL_MASS_PCT),
        "peaks": [{"price": round(p, 3), "mass_pct": round(m, 2)} for m, p, _ in peaks[:6]],
        "tier": classify_tier(profit_ratio, contains, rebound),
    }
