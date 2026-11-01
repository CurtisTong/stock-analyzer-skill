"""
趋势与结构分析（支撑阻力、箱体、突破、波浪）。
依赖: core (_find_swing_points)
"""

import statistics

from .core import _find_swing_points


def support_resistance(closes, highs, lows, ma_info):
    """关键支撑/阻力位。"""
    if len(highs) < 10 or len(lows) < 10:
        # v1.28.0：早退分支补齐键——report.py 用 sr["nearest_support"] 直接下标，
        # 缺键会 KeyError（此前只有 supports/resistances 两个键）。
        return {
            "supports": [],
            "resistances": [],
            "nearest_support": None,
            "nearest_resistance": None,
            "recent_swing_highs": [],
            "breakout_target": None,
        }

    last = closes[-1]

    # 前高前低
    lookback = min(60, len(highs))
    recent_highs = highs[-lookback:]
    recent_lows = lows[-lookback:]

    # 找局部摇摆点
    # v1.28.0 修复：摆动低点必须**单独对 lows 调用**。
    # 原实现只对 highs 调一次 _find_swing_points，然后拿返回的 pl（highs 序列
    # 自身的局部极小值索引）去索引 recent_lows —— 两个坐标系无关，取到的是
    # 随机位（实测输出"前低 18.0"而真实摆动低点是 10.0）。
    # 前低支撑标 strength="强"，并直接进入报告的"关键支撑"与止损百分比。
    ph, _pl_highs = _find_swing_points(recent_highs, window=3)
    _ph_lows, pl = _find_swing_points(recent_lows, window=3)
    all_swing_highs = sorted(set(round(recent_highs[i], 2) for i in ph))
    swing_highs = [h for h in all_swing_highs if h > last]
    swing_lows = sorted(set(round(recent_lows[i], 2) for i in pl if recent_lows[i] < last), reverse=True)

    # 突破目标：现价下方最近的摆动高点（供 breakout_check 检测"突破前高"）。
    # 与 nearest_resistance（现价上方最近阻力，供报告/止盈）区分：
    # 突破检测需要"已越过"的目标位，阻力位需要"尚未到达"的目标位。
    below_highs = [h for h in all_swing_highs if h < last]
    breakout_target = max(below_highs) if below_highs else None

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
    # v1.28.0 修复：取**最近**的 2 个，与前低支撑口径对称。
    # 原实现用 swing_highs[-2:]（升序取末尾 = 最高 = 离现价最远的两个），
    # 把真正的最近阻力丢掉（实测 nearest_resistance=28 而真实最近前高 23.0）。
    for hv in sorted(swing_highs)[:2]:
        resistances.append({"level": hv, "source": "前高", "strength": "强"})

    # 整数关口
    # v1.28.0 修复：锚点与步长口径一致。
    # 原实现锚点取十位（round(last,-1)）而 10<=last<50 时步长取 1，
    # 于是"最近的整数关口"被整体跳过（last=15 → 只给 20/21/22，跳过 16），
    # 且 round() 是 banker&apos;s rounding（round(25,-1)=20、round(35,-1)=40）行为不连续。
    # 现在锚点按步长对齐（向下取整），保证最近的关口不会被跳过。
    step = 10 if last >= 50 else 1
    round_num = round(last / step) * step if step > 1 else int(last)
    if round_num < last:
        # 最近整数关口在价格下方 → 支撑（含关口本身）
        base = round_num
        for i in range(4):
            r = base - i * step
            if r > 0:
                supports.append({"level": r, "source": "整数关口", "strength": "弱"})
    else:
        # 最近整数关口在价格上方（或恰在此）→ 阻力（含关口本身）
        base = round_num if round_num > last else round_num + step
        for i in range(3):
            resistances.append(
                {
                    "level": base + i * step,
                    "source": "整数关口",
                    "strength": "弱",
                }
            )

    # 去重排序
    # v1.28.0：同价位去重——前低 50.0 与整数关口 50.0 是同一个价格点，
    # 两条来源重复列出（报告里出现两行同一价位）。保留强度更高的那条。
    def _dedup_by_level(items):
        seen = set()
        out = []
        for it in items:
            lv = it["level"]
            if lv in seen:
                continue
            seen.add(lv)
            out.append(it)
        return out

    supports = _dedup_by_level(sorted(supports, key=lambda x: x["level"], reverse=True))[:5]
    resistances = _dedup_by_level(sorted(resistances, key=lambda x: x["level"]))[:5]

    nearest_support = supports[0]["level"] if supports else None
    nearest_resistance = resistances[0]["level"] if resistances else None

    return {
        "supports": supports[:4],
        "resistances": resistances[:4],
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "recent_swing_highs": all_swing_highs,
        "breakout_target": breakout_target,
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
    in_box = sum(1 for c in closes[-window:] if ll + (hh - ll) * 0.1 < c < hh - (hh - ll) * 0.1)
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
    avg_vol20 = statistics.mean(volumes[-21:-1]) if len(volumes) >= 21 else statistics.mean(volumes[:-1])
    last_vol = volumes[-1]

    broke = last > resistance and prev <= resistance
    if broke:
        vol_confirm = last_vol > 1.5 * avg_vol20
        return {
            "status": "突破确认(放量)" if vol_confirm else "突破待确认(缩量)",
            "resistance": round(resistance, 2),
            "volume_ratio": round(last_vol / avg_vol20, 2) if avg_vol20 > 0 else 0,
        }

    # M2 修复：原实现"回踩确认中"分支实际不可达——
    #   recent_above = all(c > resistance for c in closes[-5:]) 含今日，
    #   而非 broke 时今日必 <= resistance，该分支恒为 False。
    # 现按语义重构：
    #   - 近 5 日（不含今日）曾收于阻力上方 = 此前突破过；
    #   - 今日回落至阻力 ±1% 内 = 回踩测试支撑；
    #   - 今日仍收于阻力上方 = 突破后运行维持。
    previously_above = any(c > resistance for c in closes[-5:-1])
    if last > resistance:
        return {"status": "突破维持(回踩未破)", "resistance": round(resistance, 2)}
    if previously_above and last >= resistance * 0.99:
        return {"status": "回踩确认中", "resistance": round(resistance, 2)}
    return {"status": "未突破"}


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
        # P1-x: 用摆动点对应的收盘价比较而非索引
        # 原实现比较摆动点索引，索引恒递增导致下跌浪分支不可达
        last_ph = c[recent_ph[-1]]
        first_ph = c[recent_ph[0]]
        last_pl = c[recent_pl[-1]]
        first_pl = c[recent_pl[0]]
        if last_ph > first_ph and last_pl > first_pl:
            return "上升浪(高点抬高+低点抬高)"
        elif last_ph < first_ph and last_pl < first_pl:
            return "下跌浪(高点降低+低点降低)"
        elif last_ph > first_ph:
            return "可能有顶部结构(高点抬高但MACD需确认)"
        elif last_pl > first_pl:
            return "可能有底部结构(低点抬高)"
    return "盘整"
