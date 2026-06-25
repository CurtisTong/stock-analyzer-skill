"""
MACD 指标（含背离检测）。
依赖: core (_ema_series, _find_swing_points)
"""

from .core import _ema_series, _find_swing_points


def macd_full(closes):
    """MACD 完整分析：DIF/DEA/柱/金叉死叉 + 顶背离/底背离。"""
    if len(closes) < 34:
        return None

    # 计算 EMA 序列（ema12 比 ema26 多 14 个元素，需对齐）
    ema12_series = _ema_series(closes, 12)
    ema26_series = _ema_series(closes, 26)
    offset = len(ema12_series) - len(ema26_series)  # = 14
    dif_series = [
        ema12_series[offset + i] - ema26_series[i] for i in range(len(ema26_series))
    ]

    # 当前值取序列末尾
    dif = dif_series[-1] if dif_series else 0.0

    dea_series = _ema_series(dif_series, 9)
    dea = dea_series[-1] if dea_series else dif
    prev_dif = dif_series[-2] if len(dif_series) >= 2 else dif
    prev_dea = dea_series[-2] if len(dea_series) >= 2 else dea
    macd_bar = (dif - dea) * 2

    # 金叉死叉检测
    signal = 0
    if prev_dif <= prev_dea and dif > dea:
        signal = 1
    elif prev_dif >= prev_dea and dif < dea:
        signal = -1

    # 柱状图趋势
    prev_bar = (prev_dif - prev_dea) * 2
    if macd_bar > 0 and macd_bar > prev_bar:
        bar_trend = "红柱放大"
    elif macd_bar > 0 and macd_bar <= prev_bar:
        bar_trend = "红柱缩小"
    elif macd_bar < 0 and macd_bar < prev_bar:
        bar_trend = "绿柱放大"
    else:
        bar_trend = "绿柱缩小"

    # 背离检测
    divergence = _detect_macd_divergence(closes, dif_series, dea_series)

    return {
        "dif": round(dif, 4),
        "dea": round(dea, 4),
        "macd_bar": round(macd_bar, 4),
        "signal": signal,
        "signal_desc": {1: "金叉", -1: "死叉", 0: "无"}.get(signal),
        "bar_trend": bar_trend,
        "divergence": divergence,
    }


def _detect_macd_divergence(closes, dif_series, dea_series):
    """检测 MACD 顶背离/底背离。"""
    if len(dif_series) < 60:
        return None

    # dif_series 比 closes 短 25 个元素（EMA26 warmup），需对齐到相同时间段
    lookback = min(60, len(dif_series))
    c = closes[-lookback - (len(closes) - len(dif_series)) :][:lookback]
    d = dif_series[-lookback:]

    price_highs, price_lows = _find_swing_points(c, window=5)
    dif_highs, dif_lows = _find_swing_points(d, window=5)

    # 顶背离：价格新高而 DIF 未新高
    if len(price_highs) >= 2:
        last2_p = sorted(price_highs[-2:])
        if last2_p[1] - last2_p[0] >= 8:
            if c[last2_p[1]] > c[last2_p[0]]:
                # 找到对应的 DIF 峰值（最近邻匹配，容差与 swing window 一致）
                def _nearest_peak(peaks, target):
                    if not peaks:
                        return None
                    return min(peaks, key=lambda p: abs(p - target))

                p0_dif = _nearest_peak(dif_highs, last2_p[0])
                p1_dif = _nearest_peak(dif_highs, last2_p[1])
                if p0_dif is not None and p1_dif is not None and p0_dif != p1_dif:
                    if d[p1_dif] < d[p0_dif]:
                        return "顶背离(看跌)"

    # 底背离：价格新低而 DIF 未新低
    if len(price_lows) >= 2:
        last2_p = sorted(price_lows[-2:])
        if last2_p[1] - last2_p[0] >= 8:
            if c[last2_p[1]] < c[last2_p[0]]:

                def _nearest_low(lows, target):
                    if not lows:
                        return None
                    return min(lows, key=lambda p: abs(p - target))

                p0_dif = _nearest_low(dif_lows, last2_p[0])
                p1_dif = _nearest_low(dif_lows, last2_p[1])
                if p0_dif is not None and p1_dif is not None and p0_dif != p1_dif:
                    if d[p1_dif] > d[p0_dif]:
                        return "底背离(看涨)"

    return None
