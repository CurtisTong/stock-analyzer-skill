"""
趋势与结构分析（支撑阻力、箱体、突破、波浪）。
依赖: core (_find_swing_points)
"""

import statistics

from .core import _find_swing_points


def support_resistance(closes, highs, lows, ma_info):
    """关键支撑/阻力位。"""
    if len(highs) < 10 or len(lows) < 10:
        return {"supports": [], "resistances": []}

    last = closes[-1]

    # 前高前低
    lookback = min(60, len(highs))
    recent_highs = highs[-lookback:]
    recent_lows = lows[-lookback:]

    # 找局部摇摆点
    ph, pl = _find_swing_points(recent_highs, window=3)
    swing_highs = sorted(
        set(round(recent_highs[i], 2) for i in ph if recent_highs[i] > last)
    )
    swing_lows = sorted(
        set(round(recent_lows[i], 2) for i in pl if recent_lows[i] < last), reverse=True
    )

    supports = []
    resistances = []

    # 均线支撑/阻力
    for name, price in ma_info.get("ma_supports", [])[:3]:
        supports.append({"level": price, "source": name, "strength": "中"})
    for name, price in ma_info.get("ma_resistances", [])[:3]:
        resistances.append({"level": price, "source": name, "strength": "中"})

    # 前低支撑
    for lv in swing_lows[:2]:
        supports.append({"level": lv, "source": "前低", "strength": "强"})

    # 前高阻力
    for hv in swing_highs[-2:]:
        resistances.append({"level": hv, "source": "前高", "strength": "强"})

    # 整数关口
    round_num = round(last, -1 if last >= 10 else 0)
    if round_num < last:
        base = round_num
        for i in range(1, 4):
            r = base - i * (10 if last >= 50 else 1)
            if r > 0:
                supports.append({"level": r, "source": "整数关口", "strength": "弱"})
    else:
        base = round_num + (10 if last >= 50 else 1)
        for i in range(3):
            resistances.append(
                {
                    "level": base + i * (10 if last >= 50 else 1),
                    "source": "整数关口",
                    "strength": "弱",
                }
            )

    # 去重排序
    supports = sorted(supports, key=lambda x: x["level"], reverse=True)[:5]
    resistances = sorted(resistances, key=lambda x: x["level"])[:5]

    nearest_support = supports[0]["level"] if supports else None
    nearest_resistance = resistances[0]["level"] if resistances else None

    return {
        "supports": supports[:3],
        "resistances": resistances[:3],
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
    }


def box_detection(highs, lows, closes, window=20):
    """箱体震荡检测。"""
    if len(closes) < window:
        return None
    hh = max(highs[-window:])
    ll = min(lows[-window:])
    avg = statistics.mean(closes[-window:])
    range_pct = (hh - ll) / avg if avg > 0 else 0

    if range_pct < 0.03:
        return None

    mid = (hh + ll) / 2
    in_box = sum(
        1 for c in closes[-window:] if ll + (hh - ll) * 0.1 < c < hh - (hh - ll) * 0.1
    )
    if in_box / window >= 0.6:
        return {
            "top": round(hh, 2),
            "bottom": round(ll, 2),
            "mid": round(mid, 2),
            "range_pct": round(range_pct * 100, 1),
            "days": window,
            "status": "箱体震荡",
            "position": round((closes[-1] - ll) / (hh - ll) * 100) if hh != ll else 50,
        }
    return None


def breakout_check(closes, highs, volumes, resistance):
    """突破检测。"""
    if len(closes) < 21:
        return {"status": "数据不足"}
    last = closes[-1]
    prev = closes[-2]
    avg_vol20 = (
        statistics.mean(volumes[-21:-1])
        if len(volumes) >= 21
        else statistics.mean(volumes[:-1])
    )
    last_vol = volumes[-1]

    broke = last > resistance and prev <= resistance
    if not broke:
        # 之前突破现在回踩
        recent_above = all(c > resistance for c in closes[-5:])
        if recent_above and last < resistance * 1.01:
            return {"status": "回踩确认中", "resistance": round(resistance, 2)}
        return {"status": "未突破"}

    vol_confirm = last_vol > 1.5 * avg_vol20
    return {
        "status": "突破确认(放量)" if vol_confirm else "突破待确认(缩量)",
        "resistance": round(resistance, 2),
        "volume_ratio": round(last_vol / avg_vol20, 2) if avg_vol20 > 0 else 0,
    }


def wave_state(closes, highs, lows):
    """简易波浪状态。"""
    if len(closes) < 40:
        return "数据不足"
    lookback = min(60, len(closes))
    c = closes[-lookback:]
    ph, pl = _find_swing_points(c, window=5)

    if len(ph) >= 2 and len(pl) >= 2:
        recent_ph = sorted(ph[-3:]) if len(ph) >= 3 else sorted(ph)
        recent_pl = sorted(pl[-3:]) if len(pl) >= 3 else sorted(pl)
        if recent_ph[-1] > recent_ph[0] and recent_pl[-1] > recent_pl[0]:
            return "上升浪(高点抬高+低点抬高)"
        elif recent_ph[-1] < recent_ph[0] and recent_pl[-1] < recent_pl[0]:
            return "下跌浪(高点降低+低点降低)"
        elif recent_ph[-1] > recent_ph[0]:
            return "可能有顶部结构(高点抬高但MACD需确认)"
        elif recent_pl[-1] > recent_pl[0]:
            return "可能有底部结构(低点抬高)"
    return "盘整"
