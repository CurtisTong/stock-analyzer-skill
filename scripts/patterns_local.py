#!/usr/bin/env python3
"""
A 股本土战法形态识别。
包含：三阴一阳、老鸭头、美人肩、双针探底、涨停双响炮、底部首板。
纯技术形态识别，不依赖财务数据。
"""
import math
from common import to_float, board_type as _board_type


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def _sma(values, period):
    """简单移动平均。"""
    if len(values) < period:
        return []
    result = []
    for i in range(period - 1, len(values)):
        result.append(sum(values[i - period + 1:i + 1]) / period)
    return result


def _ema(values, period):
    """指数移动平均。"""
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    result = [sum(values[:period]) / period]
    for v in values[period:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def _is_bearish(open_p, close_p):
    """阴线：收盘低于开盘。"""
    return close_p < open_p


def _is_bullish(open_p, close_p):
    """阳线：收盘高于开盘。"""
    return close_p >= open_p


def _lower_shadow(open_p, close_p, low_p):
    """下影线长度/实体比例。"""
    body_low = min(open_p, close_p)
    shadow = body_low - low_p
    body = abs(close_p - open_p)
    return shadow / max(body, 0.001)


def _upper_shadow(open_p, close_p, high_p):
    """上影线长度/实体比例。"""
    body_high = max(open_p, close_p)
    shadow = high_p - body_high
    body = abs(close_p - open_p)
    return shadow / max(body, 0.001)


def _body_pct(open_p, close_p):
    """实体涨跌幅百分比。"""
    return (close_p - open_p) / max(open_p, 0.001) * 100


def _is_limit_up(open_p, close_p, prev_close, board):
    """检测涨停（考虑板块涨跌幅限制）。"""
    limit_ratio = {"主板": 9.5, "创业板": 19.5, "科创板": 19.5, "北交所": 29.5}.get(board, 9.5)
    chg = (close_p - prev_close) / max(prev_close, 0.001) * 100
    return chg >= limit_ratio * 0.95


# ═══════════════════════════════════════════════════════════════
# 1. 三阴一阳 / 三阳一阴
# ═══════════════════════════════════════════════════════════════

def detect_sanying_yiyang(records, volumes, code=""):
    """
    三阴一阳（洗盘后拉升）和三阳一阴（诱多后出货）。
    三阴一阳：连续3根阴线（缩量递减）→ 1根阳线覆盖前阴（放量）。
    三阳一阴：连续3根阳线（缩量递减）→ 1根阴线覆盖前阳（放量）。
    """
    if len(records) < 4:
        return []

    results = []

    for i in range(3, len(records)):
        r0, r1, r2, r3 = records[i - 3], records[i - 2], records[i - 1], records[i]
        o0, c0, o1, c1, o2, c2, o3, c3 = [to_float(r.get(k)) for r in [r0, r1, r2, r3]
                                          for k in ["open", "close"]]
        v0, v1, v2, v3 = [to_float(r.get("volume")) for r in [r0, r1, r2, r3]]

        # ── 三阴一阳（底部洗盘结束）──
        if all(_is_bearish(o, c) for o, c in [(o0, c0), (o1, c1), (o2, c2)]) and _is_bullish(o3, c3):
            # 三阴实体递减
            body0, body1, body2 = abs(c0 - o0), abs(c1 - o1), abs(c2 - o2)
            if body2 < body1 < body0:
                # 阳线收盘覆盖至少前2根阴线收盘
                if c3 > c1 and c3 > c0:
                    # 放量
                    if v3 > max(v0, v1, v2) * 1.3:
                        # 计算覆盖力度
                        coverage = (c3 - c0) / max(abs(c0 - o0), 0.001)
                        confidence = "高" if coverage > 0.8 and v3 > max(v0, v1, v2) * 1.5 else "中"
                        results.append({
                            "name": "三阴一阳",
                            "type": "看涨",
                            "date": r3.get("day", ""),
                            "desc": f"连续3阴缩量洗盘后放量阳线覆盖，覆盖力度{coverage:.1%}",
                            "confidence": confidence,
                            "idx": i,
                        })

        # ── 三阳一阴（高位诱多出货）──
        if all(_is_bullish(o, c) for o, c in [(o0, c0), (o1, c1), (o2, c2)]) and _is_bearish(o3, c3):
            body0, body1, body2 = abs(c0 - o0), abs(c1 - o1), abs(c2 - o2)
            if body2 < body1 < body0:
                if c3 < c1 and c3 < c0:
                    if v3 > max(v0, v1, v2) * 1.3:
                        results.append({
                            "name": "三阳一阴",
                            "type": "看跌",
                            "date": r3.get("day", ""),
                            "desc": "连续3阳缩量上涨后放量阴线吞没",
                            "confidence": "中",
                            "idx": i,
                        })

    return results


# ═══════════════════════════════════════════════════════════════
# 2. 老鸭头
# ═══════════════════════════════════════════════════════════════

def detect_laoyatou(records, closes, volumes, mas):
    """
    老鸭头形态：三阶段（鸭颈 → 鸭头 → 鸭嘴）。
    鸭颈：MA5 > MA10 > MA20，股价沿MA5上行
    鸭头：MA5下穿MA10形成凹坑，股价回调但未跌破MA60
    鸭嘴：MA5重新上穿MA10，放量突破前高
    """
    if len(closes) < 60 or "ma5" not in mas or "ma10" not in mas or "ma20" not in mas or "ma60" not in mas:
        return []

    ma5, ma10, ma20, ma60 = mas["ma5"], mas["ma10"], mas["ma20"], mas["ma60"]

    # 最小长度
    if len(ma60) < 20:
        return []

    # 统一用 ma60 长度作为基准（最短的 MA），对齐索引
    # ma60 对应 closes[59:], ma20 对应 closes[19:]
    # 在 ma60 索引空间工作，closes 偏移 = 59
    cl_offset = len(closes) - len(ma60)
    ma5_offset = len(ma5) - len(ma60)
    ma10_offset = len(ma10) - len(ma60)
    ma20_offset = len(ma20) - len(ma60)

    results = []

    # 扫描鸭嘴形成点（MA5 刚上穿 MA10），从 ma60 空间找
    for i_ma60 in range(20, len(ma60)):
        i5 = i_ma60 + ma5_offset
        i10 = i_ma60 + ma10_offset
        ci = i_ma60 + cl_offset

        if i5 < 1 or ci >= len(closes):
            continue

        # MA5 刚金叉 MA10
        if not (ma5[i5 - 1] <= ma10[i10 - 1] and ma5[i5] > ma10[i10]):
            continue

        # 回溯找鸭头：前 5-15 天内 MA5/10 下穿点
        duck_head_j = None
        for j_ma60 in range(max(i_ma60 - 15, 5), i_ma60 - 2):
            j5 = j_ma60 + ma5_offset
            j10 = j_ma60 + ma10_offset
            if j5 < 1:
                continue
            if ma5[j5] < ma10[j10] and ma5[j5] < ma5[j5 - 1]:
                # 确保鸭头时股价在 MA60 上方
                j_ci = j_ma60 + cl_offset
                if closes[j_ci] > ma60[j_ma60] * 0.95:
                    duck_head_j = j_ma60
                    break

        if duck_head_j is None:
            continue

        # 验证鸭颈：鸭头之前的上升趋势（MA5 > MA10 > MA20 至少3天）
        neck_days = 0
        for k_ma60 in range(max(duck_head_j - 10, 0), duck_head_j - 1):
            k5 = k_ma60 + ma5_offset
            k10 = k_ma60 + ma10_offset
            k20 = k_ma60 + ma20_offset
            if k20 >= 0 and k5 < len(ma5) and k20 < len(ma20):
                if ma5[k5] > ma10[k10] > ma20[k20]:
                    neck_days += 1

        if neck_days < 3:
            continue

        # 验证鸭嘴：放量 + 突破前高
        head_ci = duck_head_j + cl_offset
        lookback = min(head_ci, 10)
        prev_high = max(closes[head_ci - lookback:head_ci]) if lookback >= 1 else closes[head_ci]

        vol_recent = [volumes[k] for k in range(max(ci - 3, 0), ci + 1)]
        vol_older = [volumes[k] for k in range(max(head_ci - 3, 0), head_ci + 1)]
        avg_recent = sum(vol_recent) / max(len(vol_recent), 1)
        avg_older = sum(vol_older) / max(len(vol_older), 1)
        vol_expanding = avg_recent > avg_older * 1.2

        breakout = closes[ci] > prev_high * 1.02

        if vol_expanding and breakout:
            confidence = "高" if closes[ci] > prev_high * 1.05 else "中"
            results.append({
                "name": "老鸭头",
                "type": "看涨",
                "date": records[ci].get("day", ""),
                "desc": f"鸭嘴确认：MA5重上MA10+放量突破前高{prev_high:.2f}",
                "confidence": confidence,
                "idx": ci,
            })

    return results


# ═══════════════════════════════════════════════════════════════
# 3. 美人肩
# ═══════════════════════════════════════════════════════════════

def detect_meirenjian(records, closes, highs, lows, volumes, mas):
    """
    美人肩：强势上升后 2-5 日横盘（不破 MA10）+ 缩量后放量突破。
    必须在上升趋势确认的前提下（股价在 MA5/MA10 上方）。
    """
    if len(closes) < 20 or "ma5" not in mas or "ma10" not in mas:
        return []

    ma5 = mas["ma5"]
    ma10 = mas["ma10"]

    # 统一用 ma10 长度作为基准（较短的那个）
    base_len = min(len(ma5), len(ma10))
    if base_len < 15:
        return []

    offset5 = len(ma5) - base_len
    offset10 = len(ma10) - base_len
    cl_offset = len(closes) - base_len

    results = []

    for i_base in range(14, base_len):
        i5 = i_base + offset5
        i10 = i_base + offset10
        ci = i_base + cl_offset
        if ci < 14 or ci >= len(closes):
            continue

        # 条件1：横盘前为上升趋势（过去5天 MA5斜率 > 0）
        pre_slope = ma5[i5 - 5] - ma5[i5 - 10] if i5 >= 10 else 0
        if pre_slope <= 0:
            continue

        # 条件2：最近 2-5 天横盘（价格振幅 2-5%，不破 MA10）
        consolidation_range = range(max(ci - 5, 0), ci)
        price_high = max(highs[j] for j in consolidation_range) if consolidation_range else closes[ci]
        price_low = min(lows[j] for j in consolidation_range) if consolidation_range else closes[ci]
        amplitude = (price_high - price_low) / max(price_low, 0.001) * 100

        if not (2 <= amplitude <= 5):
            continue

        # 横盘期间不破 MA10
        if price_low < ma10[i10]:
            continue

        # 条件3：横盘期间缩量（vs 横盘前5天）
        consol_vol = [volumes[j] for j in consolidation_range]
        pre_vol = [volumes[j] for j in range(max(ci - 10, 0), max(ci - 5, 0))]
        if not consol_vol or not pre_vol:
            continue
        if sum(consol_vol) / len(consol_vol) > sum(pre_vol) / max(len(pre_vol), 1) * 0.7:
            continue

        # 条件4：今日放量突破横盘区间
        if volumes[ci] > sum(consol_vol) / len(consol_vol) * 1.5 and closes[ci] > price_high:
            results.append({
                "name": "美人肩",
                "type": "看涨",
                "date": records[ci].get("day", ""),
                "desc": f"横盘{len(consolidation_range)}日振幅{amplitude:.1f}%不破MA10后放量突破",
                "confidence": "高" if volumes[ci] > sum(consol_vol) / len(consol_vol) * 2 else "中",
                "idx": ci,
            })

    return results


# ═══════════════════════════════════════════════════════════════
# 4. 双针探底
# ═══════════════════════════════════════════════════════════════

def detect_shuangzhen(records, closes, lows, volumes):
    """
    双针探底：5 日内两根长下影线触及相近价位 + 缩量。
    长下影标准：下影线 > 实体 × 2 或 > 上影线 × 3。
    """
    if len(records) < 5:
        return []

    results = []

    for i in range(5, len(records)):
        window = records[i - 5:i + 1]
        w_lows = lows[i - 5:i + 1]
        w_vol = volumes[i - 5:i + 1]

        # 找长下影线
        needle_days = []
        for j, r in enumerate(window):
            o, c, l, h = to_float(r.get("open")), to_float(r.get("close")), \
                         to_float(r.get("low")), to_float(r.get("high"))
            body = abs(c - o)
            lower = min(o, c) - l
            upper = h - max(o, c)
            if lower > body * 2 and lower > upper * 3 and body > 0:
                needle_days.append({"idx": i - 5 + j, "low": l, "shadow": lower})

        # 至少2根长下影，低点接近（<2% 差异）
        if len(needle_days) >= 2:
            for a in range(len(needle_days)):
                for b in range(a + 1, len(needle_days)):
                    na, nb = needle_days[a], needle_days[b]
                    if nb["idx"] - na["idx"] < 1:
                        continue
                    low_diff = abs(na["low"] - nb["low"]) / max(na["low"], 0.001) * 100
                    if low_diff < 2:
                        # 确认缩量
                        vol_needle = [volumes[na["idx"]], volumes[nb["idx"]]]
                        vol_others = [v for j, v in enumerate(w_vol)
                                      if i - 5 + j not in (na["idx"], nb["idx"])]
                        if sum(vol_needle) / 3 < sum(vol_others) / max(len(vol_others), 1) * 0.8:
                            results.append({
                                "name": "双针探底",
                                "type": "看涨",
                                "date": records[nb["idx"]].get("day", ""),
                                "desc": f"两低点{na['low']:.2f}/{nb['low']:.2f}差异{low_diff:.1f}%，缩量触底",
                                "confidence": "高" if low_diff < 1 else "中",
                                "idx": nb["idx"],
                            })

    return results


# ═══════════════════════════════════════════════════════════════
# 5. 涨停双响炮
# ═══════════════════════════════════════════════════════════════

def detect_zhangting(records, closes, volumes, code=""):
    """
    涨停双响炮：涨停 → 1-3 日缩量整理 → 再次涨停放量。
    用于确认强势股的二次攻击信号。
    """
    if len(records) < 5:
        return []

    board = _board_type(code) if code else "主板"

    results = []

    for i in range(4, len(records)):
        r_now = records[i]
        o_now, c_now, v_now = to_float(r_now.get("open")), to_float(r_now.get("close")), to_float(r_now.get("volume"))

        # 当天必须是涨停
        prev_close_now = to_float(records[i - 1].get("close"))
        if not _is_limit_up(o_now, c_now, prev_close_now, board):
            continue

        # 回溯 1-3 天整理
        for gap in range(1, 4):
            zt1_idx = i - gap - 1
            if zt1_idx < 0:
                continue

            r_zt1 = records[zt1_idx]
            o1, c1, v1 = to_float(r_zt1.get("open")), to_float(r_zt1.get("close")), to_float(r_zt1.get("volume"))
            prev_close_1 = to_float(records[zt1_idx - 1].get("close")) if zt1_idx > 0 else c1

            # 第一次涨停
            if not _is_limit_up(o1, c1, prev_close_1, board):
                continue

            # 中间整理期：缩量 + 收盘不破第一次涨停实体中点
            zt1_mid = (o1 + c1) / 2
            consolidation_ok = True
            for k in range(zt1_idx + 1, i):
                vk = volumes[k]
                ck = closes[k]
                if vk > v1 * 0.6 or ck < zt1_mid:
                    consolidation_ok = False
                    break

            if not consolidation_ok:
                continue

            # 第二次涨停比第一次放量
            if v_now > v1 * 1.2:
                results.append({
                    "name": "涨停双响炮",
                    "type": "看涨",
                    "date": r_now.get("day", ""),
                    "desc": f"首板{gap + 1}日前+{gap}日缩量整理+今日再封板放量",
                    "confidence": "高" if gap == 1 and v_now > v1 * 1.5 else "中",
                    "idx": i,
                })
                break

    return results


# ═══════════════════════════════════════════════════════════════
# 6. 底部首板
# ═══════════════════════════════════════════════════════════════

def detect_dibu_shouban(records, closes, highs, lows, volumes, code=""):
    """
    底部首板：下跌趋势后首个涨停 → 2-3 日缩量回踩不破涨停日低点 → 确认。
    """
    if len(records) < 20:
        return []

    board = _board_type(code) if code else "主板"

    results = []

    for i in range(10, len(records) - 3):
        r_zt = records[i]
        o_zt, c_zt, h_zt, l_zt = [to_float(r_zt.get(k)) for k in ["open", "close", "high", "low"]]
        v_zt = to_float(r_zt.get("volume"))
        prev_close = to_float(records[i - 1].get("close"))

        # 当天涨停
        if not _is_limit_up(o_zt, c_zt, prev_close, board):
            continue

        # 涨停前处于下跌趋势（过去10天最高价低于20天前的高点）
        recent_high = max(highs[i - 10:i]) if i >= 10 else highs[i]
        older_high = max(highs[max(i - 20, 0):i - 10]) if i >= 20 else recent_high
        if recent_high > older_high * 0.95:
            continue

        # 涨停前 5 天有过下跌
        pre_change = (closes[i - 1] - closes[i - 5]) / max(closes[i - 5], 0.001) * 100 if i >= 5 else 0
        if pre_change > -5:
            continue

        # 未来 2-3 日回踩：缩量 + 收盘不破涨停日低点
        backtest_ok = True
        min_vol = float("inf")
        for k in range(i + 1, min(i + 4, len(records))):
            if closes[k] < l_zt * 0.98:
                backtest_ok = False
                break
            min_vol = min(min_vol, volumes[k])

        if not backtest_ok:
            continue

        # 缩量确认（回踩期间均量 < 涨停日量 × 0.5）
        if min_vol < v_zt * 0.5:
            # 确认点：缩量后出现阳线
            for k in range(i + 1, min(i + 4, len(records))):
                rk = records[k]
                ok, ck = to_float(rk.get("open")), to_float(rk.get("close"))
                if _is_bullish(ok, ck) and volumes[k] > min_vol * 1.2:
                    results.append({
                        "name": "底部首板",
                        "type": "看涨",
                        "date": rk.get("day", ""),
                        "desc": f"下跌后首板+{k - i}日缩量回踩不破涨停低点{l_zt:.2f}",
                        "confidence": "高" if k - i <= 2 else "中",
                        "idx": k,
                    })
                    break

    return results


# ═══════════════════════════════════════════════════════════════
# 顶层整合
# ═══════════════════════════════════════════════════════════════

def detect_all_local_patterns(records, closes, highs, lows, volumes, mas, code=""):
    """
    运行所有本土战法形态识别，返回汇总结果。

    Args:
        records: K 线数据 list
        closes: 收盘价序列
        highs: 最高价序列
        lows: 最低价序列
        volumes: 成交量序列
        mas: 移动平均线 dict {"ma5": [...], "ma10": [...], "ma20": [...], "ma60": [...]}
        code: 股票代码（用于板块判断）

    Returns:
        {
            "patterns": [{"name": ..., "type": ..., "date": ..., "desc": ..., "confidence": ...}],
            "summary": "...",
            "count": N,
        }
    """
    all_patterns = []

    # 三阴一阳/三阳一阴
    all_patterns.extend(detect_sanying_yiyang(records, volumes, code))

    # 老鸭头
    all_patterns.extend(detect_laoyatou(records, closes, volumes, mas))

    # 美人肩
    all_patterns.extend(detect_meirenjian(records, closes, highs, lows, volumes, mas))

    # 双针探底
    all_patterns.extend(detect_shuangzhen(records, closes, lows, volumes))

    # 涨停双响炮
    all_patterns.extend(detect_zhangting(records, closes, volumes, code))

    # 底部首板
    all_patterns.extend(detect_dibu_shouban(records, closes, highs, lows, volumes, code))

    # 按时间排序（最新的在后）
    all_patterns.sort(key=lambda p: p["idx"])

    # 去重：同一日期同一形态只保留一次
    seen = set()
    deduped = []
    for p in all_patterns:
        key = (p["name"], p["date"])
        if key not in seen:
            seen.add(key)
            deduped.append(p)

    # 只看最近出现的（idx 最大的）
    recent = deduped[-5:] if len(deduped) > 5 else deduped

    bullish = [p["name"] for p in recent if p["type"] == "看涨"]
    bearish = [p["name"] for p in recent if p["type"] == "看跌"]

    summary_parts = []
    if bullish:
        summary_parts.append(f"看涨形态: {', '.join(bullish)}")
    if bearish:
        summary_parts.append(f"看跌形态: {', '.join(bearish)}")
    summary = "; ".join(summary_parts) if summary_parts else "未检测到本土战法形态"

    return {
        "patterns": recent,
        "summary": summary,
        "count": len(recent),
    }


# ── 命令行快速测试 ──
if __name__ == "__main__":
    import sys
    import json
    from common import normalize_quote_code
    from kline import fetch as fetch_kline

    if len(sys.argv) < 2:
        print("用法: python3 patterns_local.py <code>")
        sys.exit(1)

    code = normalize_quote_code(sys.argv[1])
    records = fetch_kline(code, 240, 250)

    closes = [to_float(r.get("close")) for r in records if to_float(r.get("close")) > 0]
    highs = [to_float(r.get("high")) for r in records]
    lows = [to_float(r.get("low")) for r in records]
    volumes = [to_float(r.get("volume")) for r in records]

    mas = {}
    for p in [5, 10, 20, 60]:
        sma = _sma(closes, p)
        mas[f"ma{p}"] = sma

    result = detect_all_local_patterns(records, closes, highs, lows, volumes, mas, code)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
