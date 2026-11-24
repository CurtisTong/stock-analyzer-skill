"""
趋势与结构分析（支撑阻力、箱体、突破、波浪）。
依赖: core (_find_swing_points)
"""

import math
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
    if below_highs:
        breakout_target = max(below_highs)
    elif len(highs) >= 21:
        # P2 修复：单边上涨时 _find_swing_points(window=3) 找不到摆动高点，
        # all_swing_highs 为空 → breakout_target=None → analyzer.py:145 根本不会
        # 调用 breakout_check。回退到近 21 根最高价（不含今日）作为"近前高"目标，
        # 让上涨趋势中的突破检测仍能运行。
        breakout_target = max(highs[-21:-1])
    else:
        breakout_target = None

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
    # v1.28.0 修复：锚点与步长口径一致（math.floor 对齐，避免银行家舍入跳变）。
    # P1 修复：原实现只算 floor(last/step)*step 并用 if/else 二选一——
    #   floor(last/step)*step <= last 恒成立，所以非倍数价只生成下方支撑、
    #   倍数价只生成上方阻力（last=20.0 时下方支撑全消失）。
    # 现在 floor/ceil 两侧都算，支撑与阻力各自独立生成，取消二选一。
    # P2 修复：按价格量级分档，边界明确归属（<10 → 0.5；10~50 → 1；≥50 → 10，
    # 含 100/200 及以上端点）。低价股引入 0.5 元细网格，避免所有价位共用单一
    # 1 元档导致的关口过粗。
    # 50/100/200 采用 10 元档为对齐习惯，属有意设计，非缺陷：A 股整数关口天然
    # 按 10 元对齐，且 T3 的 P1 测试钉死 last=49→1 元、last=50→10 元，故 50 处
    # 的网格跳变按设计保留（不再视为待修缺陷）。
    if last < 10:
        step = 0.5
    elif last < 50:
        step = 1
    else:  # last >= 50，含 100/200 及以上端点
        step = 10
    lower = math.floor(last / step) * step
    upper = math.ceil(last / step) * step
    # 现价恰在关口时的口径：该价位作为"当前关口"，既不视为已跌破的支撑、
    # 也不视为待突破的阻力，故不重复计入任一侧；下方支撑自 lower-step 起，
    # 上方阻力自 upper+step 起。这样可避免 nearest_support==现价 被
    # report.py/technical.py 误判为"破位"（它们用 nearest_support >= 现价判定）。
    # 关口为"弱"来源：为真实摆动点（前低/前高，"强"）预留名额，防止新增的
    # 双侧关口把强来源挤出最终前 4（否则会丢失真实摆动低点，影响止损位）。
    n_sup_integer = max(0, 4 - sum(1 for s in supports if s["strength"] == "强"))
    n_res_integer = max(0, 3 - sum(1 for r in resistances if r["strength"] == "强"))
    support_base = lower if lower < last else lower - step
    resistance_base = upper if upper > last else upper + step
    for i in range(n_sup_integer):
        r = support_base - i * step
        if r > 0:
            supports.append({"level": r, "source": "整数关口", "strength": "弱"})
    for i in range(n_res_integer):
        resistances.append(
            {"level": resistance_base + i * step, "source": "整数关口", "strength": "弱"}
        )

    # 去重排序
    # v1.28.0：同价位去重——前低 50.0 与整数关口 50.0 是同一个价格点，
    # 两条来源重复列出（报告里出现两行同一价位）。保留强度更高的那条。
    # P1 修复：原实现按 level 单键稳定排序，先插入的 MA20(中) 会挤掉
    # 后插入的前低(强)（复现：18.0 被标成 MA20/中）。排序键加入强度权重，
    # 同价位时 强 > 中 > 弱 优先，_dedup_by_level 保留首个（最强）来源。
    strength_rank = {"强": 0, "中": 1, "弱": 2}

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

    # 支撑按价位降序（最近支撑在前），同价位按强度降序（负 rank 配合 reverse）
    supports = _dedup_by_level(
        sorted(supports, key=lambda x: (x["level"], -strength_rank.get(x["strength"], 3)), reverse=True)
    )[:5]
    # 阻力按价位升序（最近阻力在前），同价位按强度降序
    resistances = _dedup_by_level(
        sorted(resistances, key=lambda x: (x["level"], -strength_rank.get(x["strength"], 3)))
    )[:5]

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

    # P1 修复：原判定 `range_pct < 0.03 -> None` 方向错误——把 1.4% 的
    # 窄幅箱体拒掉，却放行 33.5% 的宽幅乱象。改为双侧区间：
    # 下限 1% 防噪声，上限 20% 防宽幅误判为箱体。
    if not (0.01 <= range_pct <= 0.20):
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
            # P1 修复：range_pct >= 0.01 且 avg > 0 已保证 hh != ll，
            # 原 `if hh != ll else 50` 分支不可达，删除。
            "position": round((closes[-1] - ll) / (hh - ll) * 100),
        }
    return None


def breakout_check(closes, highs, volumes, resistance):
    """突破检测。

    口径：以**收盘价**越过阻力（且前一日未越过）判定"收盘突破"，再按量能确认；
    盘中 high 越过但收盘未站稳的，单列"盘中突破待确认(收盘回落)"——既提示突破
    尝试，又不冒充已确认突破（P2 修复：此前 highs 参数被完全忽略）。
    """
    # P1 修复：原实现对 volumes 不做检查，空量输入 [] 会在
    # statistics.mean([]) 抛 StatisticsError（复现 breakout_check([1]*21,[1]*21,[],0.5)）。
    # 量能基准至少需要 2 个值（1 个算均值 + 1 个当日量）。
    if len(closes) < 21 or len(volumes) < 2:
        return {"status": "数据不足"}
    last = closes[-1]
    prev = closes[-2]
    avg_vol20 = statistics.mean(volumes[-21:-1]) if len(volumes) >= 21 else statistics.mean(volumes[:-1])
    last_vol = volumes[-1]

    broke = last > resistance and prev <= resistance
    if broke:
        # P1 修复：avg_vol20<=0 时无法判断放量，原实现仍给出"突破确认(放量)"
        # 但 volume_ratio 写死 0（量能基准为 0 导致 1.5*0=0 < last_vol 恒真），
        # 状态与 ratio 口径矛盾。改为明确返回"量能基准无效"待确认。
        if avg_vol20 <= 0:
            return {
                "status": "突破待确认(量能基准无效)",
                "resistance": round(resistance, 2),
                "volume_ratio": 0,
            }
        vol_confirm = last_vol > 1.5 * avg_vol20
        return {
            "status": "突破确认(放量)" if vol_confirm else "突破待确认(缩量)",
            "resistance": round(resistance, 2),
            "volume_ratio": round(last_vol / avg_vol20, 2),
        }

    # M2 修复：原实现"回踩确认中"分支实际不可达——
    #   recent_above = all(c > resistance for c in closes[-5:]) 含今日，
    #   而非 broke 时今日必 <= resistance，该分支恒为 False。
    # 现按语义重构：
    #   - 近 5 日（不含今日）曾收于阻力上方 = 此前突破过；
    #   - 今日回落至阻力 ±1% 内 = 回踩测试支撑；
    #   - 今日仍收于阻力上方 = 突破后运行维持。
    # P2 修复：原切片 closes[-5:-1] 只有 4 根，与注释"近 5 日"不符；
    # 改为 [-6:-1] 才是真正的 5 根（不含今日）。
    previously_above = any(c > resistance for c in closes[-6:-1])
    if last > resistance:
        return {"status": "突破维持(回踩未破)", "resistance": round(resistance, 2)}
    if previously_above and last >= resistance * 0.99:
        return {"status": "回踩确认中", "resistance": round(resistance, 2)}
    # P2 修复：原实现只看收盘价，盘中 high 大幅越过阻力但收盘回落时误报"未突破"
    # （复现：末根 close=23、high=26、resistance=24）。放在"回踩确认中"之后，
    # 避免改写已突破后的回踩语义；highs 为空时安全跳过。
    if highs and highs[-1] > resistance:
        return {"status": "盘中突破待确认(收盘回落)", "resistance": round(resistance, 2)}
    return {"status": "未突破"}


def wave_state(closes, highs, lows):
    """简易波浪状态。"""
    if len(closes) < 40:
        return "数据不足"
    lookback = min(60, len(closes))
    c = closes[-lookback:]
    # P2 修复：原实现声明接收 highs/lows 却完全未使用——传 [999]*60/[0]*60
    # 与传原值输出相同。现按文案"高点/低点"语义，用 highs 找摆动高点、lows 找
    # 摆动低点，再取其**对应索引的收盘价**比较（保持四象限文案不变，供
    # factions.py 的"下跌浪/上升浪/顶部/扩张/底部"关键词匹配）。
    ph, _ = _find_swing_points(highs[-lookback:], window=5)
    _, pl = _find_swing_points(lows[-lookback:], window=5)

    if len(ph) >= 2 and len(pl) >= 2:
        recent_ph = sorted(ph[-3:]) if len(ph) >= 3 else sorted(ph)
        recent_pl = sorted(pl[-3:]) if len(pl) >= 3 else sorted(pl)
        # P1-x: 用摆动点对应的收盘价比较而非索引
        # 原实现比较摆动点索引，索引恒递增导致下跌浪分支不可达
        last_ph = c[recent_ph[-1]]
        first_ph = c[recent_ph[0]]
        last_pl = c[recent_pl[-1]]
        first_pl = c[recent_pl[0]]
        # P1 修复：原实现把"高点降低+低点抬高"（收敛三角形）误标为
        # "可能有底部结构"。四象限分别命名，避免把中性待突破形态当底部：
        #   双升=上升浪 / 双降=下跌浪
        #   高升低降=扩张形态/顶部风险
        #   高降低升=收敛三角形/中性待突破
        if last_ph > first_ph and last_pl > first_pl:
            return "上升浪(高点抬高+低点抬高)"
        elif last_ph < first_ph and last_pl < first_pl:
            return "下跌浪(高点降低+低点降低)"
        elif last_ph > first_ph:
            return "扩张形态/顶部风险(高点抬高+低点降低)"
        elif last_pl > first_pl:
            return "收敛三角形/中性待突破(高点降低+低点抬高)"
    return "盘整"
