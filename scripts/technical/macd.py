"""
MACD 指标（含背离检测）。
依赖: core (ema, _ema_series, _find_swing_points)
"""
from .core import ema, _ema_series, _find_swing_points


def macd_full(closes):
    """MACD 完整分析：DIF/DEA/柱/金叉死叉 + 顶背离/底背离。"""
    if len(closes) < 34:
        return None

    # DIF/DEA
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    dif = ema12 - ema26

    # 计算 DIF 序列
    ema12_series = _ema_series(closes, 12)
    ema26_series = _ema_series(closes, 26)
    min_len = min(len(ema12_series), len(ema26_series))
    dif_series = [ema12_series[i] - ema26_series[i] for i in range(min_len)]

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
    if len(closes) < 60 or len(dif_series) < 60:
        return None

    lookback = min(60, len(closes))
    c = closes[-lookback:]
    d = dif_series[-lookback:]

    price_highs, price_lows = _find_swing_points(c, window=5)
    dif_highs, dif_lows = _find_swing_points(d, window=5)

    # 顶背离：价格新高而 DIF 未新高
    if len(price_highs) >= 2:
        last2_p = sorted(price_highs[-2:])
        if last2_p[1] - last2_p[0] >= 8:
            if c[last2_p[1]] > c[last2_p[0]]:
                # 找到对应的 DIF 峰值
                relevant_dif_peaks = [i for i in dif_highs if abs(i - last2_p[0]) <= 5 or abs(i - last2_p[1]) <= 5]
                if len(relevant_dif_peaks) >= 2:
                    relevant_dif_peaks.sort()
                    if d[relevant_dif_peaks[-1]] < d[relevant_dif_peaks[0]]:
                        return "顶背离(看跌)"

    # 底背离：价格新低而 DIF 未新低
    if len(price_lows) >= 2:
        last2_p = sorted(price_lows[-2:])
        if last2_p[1] - last2_p[0] >= 8:
            if c[last2_p[1]] < c[last2_p[0]]:
                relevant_dif_lows = [i for i in dif_lows if abs(i - last2_p[0]) <= 5 or abs(i - last2_p[1]) <= 5]
                if len(relevant_dif_lows) >= 2:
                    relevant_dif_lows.sort()
                    if d[relevant_dif_lows[-1]] > d[relevant_dif_lows[0]]:
                        return "底背离(看涨)"

    return None
