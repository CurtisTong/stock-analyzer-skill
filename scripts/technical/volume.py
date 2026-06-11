"""
成交量分析（量价配合、OBV）。
依赖: core (_find_swing_points)
"""
import statistics

from .core import _find_swing_points


def volume_analysis(closes, volumes):
    """量价分析：量比、天量/地量、量价配合、OBV。"""
    if len(closes) < 6 or len(volumes) < 6:
        return None

    last = closes[-1]
    recent_vol_avg = statistics.mean(volumes[-5:]) if len(volumes) >= 5 else volumes[-1]
    base_vol_avg = statistics.mean(volumes[-20:-5]) if len(volumes) >= 20 else recent_vol_avg
    volume_ratio = recent_vol_avg / base_vol_avg if base_vol_avg > 0 else 1

    # 量比定性
    if volume_ratio < 0.3:
        vr_desc = "地量(底部信号)"
    elif volume_ratio < 0.5:
        vr_desc = "极度缩量"
    elif volume_ratio < 0.8:
        vr_desc = "缩量"
    elif volume_ratio < 1.2:
        vr_desc = "正常"
    elif volume_ratio < 2.0:
        vr_desc = "放量"
    elif volume_ratio < 3.0:
        vr_desc = "显著放量"
    else:
        vr_desc = "巨量(警惕短期高点)"

    # 量价配合
    mid = max(len(closes) // 2, 3)
    recent_c = closes[-mid:]
    prev_c = closes[:mid]
    recent_v = volumes[-mid:]
    prev_v = volumes[:mid]

    price_chg = statistics.mean(recent_c) / max(statistics.mean(prev_c), 0.01) - 1
    vol_chg = statistics.mean(recent_v) / max(statistics.mean(prev_v), 0.01) - 1

    if price_chg > 0.01 and vol_chg > 0:
        vp_desc = "放量上涨(资金介入)"
        vp_signal = 1
    elif price_chg < -0.01 and vol_chg < 0:
        vp_desc = "缩量下跌(抛压减轻)"
        vp_signal = 1
    elif price_chg > 0.01 and vol_chg < 0:
        vp_desc = "缩量上涨(量价背离)"
        vp_signal = -1
    elif price_chg < -0.01 and vol_chg > 0:
        vp_desc = "放量下跌(主力出货)"
        vp_signal = -1
    else:
        vp_desc = "量价中性"
        vp_signal = 0

    # OBV 及背离
    obv_values = _obv_series(closes, volumes)
    obv_now = obv_values[-1] if obv_values else 0
    obv_div = _detect_obv_divergence(closes, obv_values)

    return {
        "volume_ratio": round(volume_ratio, 2),
        "volume_ratio_desc": vr_desc,
        "volume_price": vp_desc,
        "volume_price_signal": vp_signal,
        "obv_divergence": obv_div,
    }


def _obv_series(closes, volumes):
    """OBV 序列。"""
    n = min(len(closes), len(volumes))
    if n == 0:
        return []
    obv = [0]
    for i in range(1, n):
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    return obv


def _detect_obv_divergence(closes, obv_series):
    """OBV 顶/底背离。"""
    if len(closes) < 40 or len(obv_series) < 40:
        return None
    lookback = min(40, len(closes))
    c = closes[-lookback:]
    o = obv_series[-lookback:]

    price_highs, price_lows = _find_swing_points(c, window=5)
    obv_highs, obv_lows = _find_swing_points(o, window=5)

    if len(price_highs) >= 2 and len(obv_highs) >= 2:
        last2_p = sorted(price_highs[-2:])
        if last2_p[1] - last2_p[0] >= 8 and c[last2_p[1]] > c[last2_p[0]]:
            relevant = sorted([i for i in obv_highs if abs(i - last2_p[0]) <= 5 or abs(i - last2_p[1]) <= 5])
            if len(relevant) >= 2 and o[relevant[-1]] < o[relevant[0]]:
                return "OBV顶背离"

    if len(price_lows) >= 2 and len(obv_lows) >= 2:
        last2_p = sorted(price_lows[-2:])
        if last2_p[1] - last2_p[0] >= 8 and c[last2_p[1]] < c[last2_p[0]]:
            relevant = sorted([i for i in obv_lows if abs(i - last2_p[0]) <= 5 or abs(i - last2_p[1]) <= 5])
            if len(relevant) >= 2 and o[relevant[-1]] > o[relevant[0]]:
                return "OBV底背离"
    return None
