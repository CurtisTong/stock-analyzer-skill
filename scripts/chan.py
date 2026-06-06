#!/usr/bin/env python3
"""
缠中说禅理论（缠论）实现。
包含：K线包含处理 → 分型 → 笔 → 线段 → 中枢 → 买卖点 → 背驰检测。
用于 A 股技术分析，纯算法实现，不依赖外部数据。
"""
import math
from common import to_float
from technical.core import _ema_series


# ═══════════════════════════════════════════════════════════════
# 1. K线包含处理
# ═══════════════════════════════════════════════════════════════

def chan_merge_inclusions(records, max_merge=3):
    """
    K线包含关系处理：连续涨势取高高，跌势取低低。
    返回合并后的 K 线列表。

    Args:
        records: K 线数据列表
        max_merge: 最大连续合并次数（A 股涨跌停适配，默认 3，设为 0 表示不限制）
    """
    if len(records) < 3:
        return records

    bars = []
    for r in records:
        bars.append({
            "high": to_float(r.get("high")),
            "low": to_float(r.get("low")),
            "open": to_float(r.get("open")),
            "close": to_float(r.get("close")),
            "date": r.get("day", ""),
            "idx": len(bars),
        })

    merged = [dict(bars[0])]
    direction = "up"  # 默认向上
    consecutive_merges = 0

    for i in range(1, len(bars)):
        prev = merged[-1]
        curr = bars[i]

        # 检查包含关系：一根K线的高低范围完全包含另一根
        curr_in_prev = curr["high"] <= prev["high"] and curr["low"] >= prev["low"]
        prev_in_curr = prev["high"] <= curr["high"] and prev["low"] >= curr["low"]

        if (curr_in_prev or prev_in_curr) and (max_merge == 0 or consecutive_merges < max_merge):
            consecutive_merges += 1
            if direction == "up":
                merged[-1] = {
                    "high": max(prev["high"], curr["high"]),
                    "low": max(prev["low"], curr["low"]),
                    "date": curr["date"],
                    "idx": curr["idx"],
                }
            else:
                merged[-1] = {
                    "high": min(prev["high"], curr["high"]),
                    "low": min(prev["low"], curr["low"]),
                    "date": curr["date"],
                    "idx": curr["idx"],
                }
        else:
            consecutive_merges = 0
            # 更新方向
            if curr["high"] > prev["high"]:
                direction = "up"
            elif curr["low"] < prev["low"]:
                direction = "down"
            merged.append(dict(curr))

    return merged


# ═══════════════════════════════════════════════════════════════
# 2. 顶底分型识别
# ═══════════════════════════════════════════════════════════════

def chan_fenxing(merged_bars):
    """
    从合并后的 K 线序列识别顶分型和底分型。
    顶分型：中间K线高点最高，且中间K线低点最高。
    底分型：中间K线低点最低，且中间K线高点最低。
    """
    if len(merged_bars) < 3:
        return []

    fenxing_list = []
    for i in range(1, len(merged_bars) - 1):
        b0, b1, b2 = merged_bars[i - 1], merged_bars[i], merged_bars[i + 1]

        # 顶分型
        if b1["high"] > b0["high"] and b1["high"] > b2["high"] and \
           b1["low"] > b0["low"] and b1["low"] > b2["low"]:
            fenxing_list.append({"type": "顶", "bar": b1, "idx": i})

        # 底分型
        elif b1["low"] < b0["low"] and b1["low"] < b2["low"] and \
             b1["high"] < b0["high"] and b1["high"] < b2["high"]:
            fenxing_list.append({"type": "底", "bar": b1, "idx": i})

    # 去重：连续同类型分型保留最强的
    deduped = []
    for fx in fenxing_list:
        if not deduped:
            deduped.append(fx)
            continue
        last = deduped[-1]
        if last["type"] == fx["type"]:
            # 同类型：顶保留更高的，底保留更低的
            if fx["type"] == "顶" and fx["bar"]["high"] > last["bar"]["high"]:
                deduped[-1] = fx
            elif fx["type"] == "底" and fx["bar"]["low"] < last["bar"]["low"]:
                deduped[-1] = fx
        else:
            deduped.append(fx)

    return deduped


# ═══════════════════════════════════════════════════════════════
# 3. 笔的构建
# ═══════════════════════════════════════════════════════════════

def chan_bi(merged_bars):
    """
    从合并K线构建笔。
    相邻顶底分型之间至少要有1根独立K线（合并后）。
    """
    fenxing_list = chan_fenxing(merged_bars)
    bi_list = []

    if len(fenxing_list) < 2:
        return bi_list

    i = 0
    while i < len(fenxing_list) - 1:
        f0, f1 = fenxing_list[i], fenxing_list[i + 1]

        # 必须交替
        if f0["type"] == f1["type"]:
            i += 1
            continue

        # 至少1根独立K线间隔
        if f1["idx"] - f0["idx"] < 2:
            i += 1
            continue

        direction = "up" if f0["type"] == "底" else "down"
        bi_list.append({
            "start": f0,
            "end": f1,
            "direction": direction,
            "high": round(max(f0["bar"]["high"], f1["bar"]["high"]), 3),
            "low": round(min(f0["bar"]["low"], f1["bar"]["low"]), 3),
            "start_idx": f0["idx"],
            "end_idx": f1["idx"],
        })
        i += 1

    return bi_list


# ═══════════════════════════════════════════════════════════════
# 4. 线段构建
# ═══════════════════════════════════════════════════════════════

def chan_xianduan(bi_list):
    """
    从笔构建线段。
    线段至少由3笔构成，前3笔必须有重叠区间。
    线段破坏判断基于初始重叠区间（前3笔），不随后续笔动态更新。
    """
    if len(bi_list) < 3:
        return []

    xd_list = []
    i = 0
    while i <= len(bi_list) - 3:
        b0, b1, b2 = bi_list[i], bi_list[i + 1], bi_list[i + 2]

        # 前三笔必须有重叠
        overlap_high = min(b0["high"], b1["high"], b2["high"])
        overlap_low = max(b0["low"], b1["low"], b2["low"])

        if overlap_low >= overlap_high:
            i += 1
            continue

        # 线段方向 = 第一笔方向
        direction = b0["direction"]

        # 固定参考点：线段起点的极值（不随后续笔更新）
        if direction == "up":
            seg_start_low = b0["low"]
        else:
            seg_start_high = b0["high"]

        # 扩展线段：加入更多笔
        j = i + 3
        while j < len(bi_list):
            next_bi = bi_list[j]
            if direction == "up":
                # 上升段：后续笔的 low 不能跌破线段起点的 low
                if next_bi["low"] >= seg_start_low:
                    j += 1
                else:
                    break
            else:
                # 下降段：后续笔的 high 不能突破线段起点的 high
                if next_bi["high"] <= seg_start_high:
                    j += 1
                else:
                    break

        seg_bis = bi_list[i:j]
        xd_list.append({
            "direction": direction,
            "bi_count": len(seg_bis),
            "start_bi": i,
            "end_bi": j - 1,
            "high": round(max(b["high"] for b in seg_bis), 3),
            "low": round(min(b["low"] for b in seg_bis), 3),
        })
        i = j

    return xd_list


# ═══════════════════════════════════════════════════════════════
# 5. 中枢识别
# ═══════════════════════════════════════════════════════════════

def chan_zhongshu(xd_list):
    """
    从线段列表识别中枢。
    中枢 = 连续3段线段的重叠区间：ZG = min(线段高点), ZD = max(线段低点)。
    相邻中枢有重叠时合并为扩展中枢。
    """
    if len(xd_list) < 3:
        return []

    zs_list = []
    for i in range(len(xd_list) - 2):
        x0, x1, x2 = xd_list[i], xd_list[i + 1], xd_list[i + 2]
        zg = min(x0["high"], x1["high"], x2["high"])
        zd = max(x0["low"], x1["low"], x2["low"])

        if zd < zg:
            zs_list.append({
                "zg": round(zg, 3),
                "zd": round(zd, 3),
                "mid": round((zg + zd) / 2, 3),
                "width": round(zg - zd, 3),
                "xd_start": i,
                "xd_end": i + 2,
            })

    # 合并重叠中枢
    if len(zs_list) <= 1:
        return zs_list

    merged_zs = [zs_list[0]]
    for zs in zs_list[1:]:
        last = merged_zs[-1]
        # 有重叠（新中枢的低点 < 旧中枢的高点）
        if zs["zd"] < last["zg"] and zs["zg"] > last["zd"]:
            merged_zs[-1] = {
                "zg": round(max(last["zg"], zs["zg"]), 3),
                "zd": round(min(last["zd"], zs["zd"]), 3),
                "mid": round((max(last["zg"], zs["zg"]) + min(last["zd"], zs["zd"])) / 2, 3),
                "width": round(max(last["zg"], zs["zg"]) - min(last["zd"], zs["zd"]), 3),
                "xd_start": last["xd_start"],
                "xd_end": zs["xd_end"],
            }
        else:
            merged_zs.append(zs)

    return merged_zs


# ═══════════════════════════════════════════════════════════════
# 6. MACD 面积计算（用于背驰检测）
# ═══════════════════════════════════════════════════════════════

def _macd_area(dif_series, dea_series, start_idx, end_idx):
    """计算 MACD 柱面积 = Σ|DIF - DEA|，用于力度对比。"""
    if start_idx < 0 or end_idx >= len(dif_series) or start_idx >= end_idx:
        return 0
    area = 0
    for i in range(start_idx, end_idx + 1):
        area += abs(dif_series[i] - dea_series[i])
    return area


# ═══════════════════════════════════════════════════════════════
# 7. 背驰检测
# ═══════════════════════════════════════════════════════════════

def chan_beichi(bi_list, zs_list, closes):
    """
    背驰检测。
    趋势背驰：比较两段同向走势的 MACD 面积，面积衰减+价格创极端=背驰。
    盘整背驰：比较中枢前后两段的力度。
    """
    if len(closes) < 34 or len(bi_list) < 4:
        return {"trend_beichi": None, "range_beichi": [], "summary": "数据不足"}

    # 计算 DIF/DEA 序列
    ema12 = _ema_series(closes, 12)
    ema26 = _ema_series(closes, 26)
    min_len = min(len(ema12), len(ema26))
    dif_series = [ema12[i] - ema26[i] for i in range(min_len)]
    dea_series = _ema_series(dif_series, 9)

    result = {"trend_beichi": None, "range_beichi": [], "summary": ""}

    # ── 趋势背驰：比较最后两段同向笔的力度 ──
    # 找最后两段下跌笔（底背驰）或上升笔（顶背驰）
    down_bis = [bi for bi in bi_list if bi["direction"] == "down"]
    up_bis = [bi for bi in bi_list if bi["direction"] == "up"]

    # 底背驰：最后两段下跌笔，第二段价格更低但 MACD 面积更小
    if len(down_bis) >= 2:
        b1, b2 = down_bis[-2], down_bis[-1]
        start1, end1 = b1["start_idx"], b1["end_idx"]
        start2, end2 = b2["start_idx"], b2["end_idx"]

        if end2 < len(dif_series) and end1 < len(dif_series):
            area1 = _macd_area(dif_series, dea_series, min(start1, len(dif_series) - 1), min(end1, len(dif_series) - 1))
            area2 = _macd_area(dif_series, dea_series, min(start2, len(dif_series) - 1), min(end2, len(dif_series) - 1))
            if area2 < area1 and b2["low"] < b1["low"]:
                result["trend_beichi"] = "底背驰(看涨)"

    # 顶背驰：最后两段上升笔，第二段价格更高但 MACD 面积更小
    if len(up_bis) >= 2 and result["trend_beichi"] is None:
        b1, b2 = up_bis[-2], up_bis[-1]
        start1, end1 = b1["start_idx"], b1["end_idx"]
        start2, end2 = b2["start_idx"], b2["end_idx"]

        if end2 < len(dif_series) and end1 < len(dif_series):
            area1 = _macd_area(dif_series, dea_series, min(start1, len(dif_series) - 1), min(end1, len(dif_series) - 1))
            area2 = _macd_area(dif_series, dea_series, min(start2, len(dif_series) - 1), min(end2, len(dif_series) - 1))
            if area2 < area1 and b2["high"] > b1["high"]:
                result["trend_beichi"] = "顶背驰(看跌)"

    # ── 盘整背驰：检查每个中枢的进入段 vs 离开段 ──
    for zs_idx, zs in enumerate(zs_list):
        # 盘整背驰：中枢前后各有一段同向走势，比较 MACD 面积
        # 进入段 = 中枢前最后一段走势（在中枢 xd_start 之前的笔）
        # 离开段 = 中枢后第一段走势（在中枢 xd_end 之后的笔）
        xd_start = zs.get("xd_start", 0)
        xd_end = zs.get("xd_end", 0)

        # 找进入段：xd_start 之前的最后一笔
        entry_bi = None
        for bi in reversed(bi_list):
            if bi["end_idx"] <= xd_start:
                entry_bi = bi
                break

        # 找离开段：xd_end 之后的第一笔
        exit_bi = None
        for bi in bi_list:
            if bi["start_idx"] >= xd_end:
                exit_bi = bi
                break

        if entry_bi and exit_bi:
            e_start, e_end = entry_bi["start_idx"], entry_bi["end_idx"]
            x_start, x_end = exit_bi["start_idx"], exit_bi["end_idx"]

            if e_end < len(dif_series) and x_end < len(dif_series):
                entry_area = _macd_area(dif_series, dea_series,
                                        min(e_start, len(dif_series) - 1),
                                        min(e_end, len(dif_series) - 1))
                exit_area = _macd_area(dif_series, dea_series,
                                       min(x_start, len(dif_series) - 1),
                                       min(x_end, len(dif_series) - 1))

                # 离开段面积 < 进入段面积 = 盘整背驰
                if exit_area < entry_area * 0.8:  # 允许 20% 容差
                    zs_mid = zs.get("mid", 0)
                    last_close = closes[-1]
                    if last_close > zs.get("zg", 0):
                        result["range_beichi"].append({
                            "zs_idx": zs_idx,
                            "type": "盘整背驰(看跌)",
                            "desc": f"中枢上方离开力度衰减(面积比{exit_area/max(entry_area,0.01):.2f})",
                        })
                    elif last_close < zs.get("zd", 0):
                        result["range_beichi"].append({
                            "zs_idx": zs_idx,
                            "type": "盘整背驰(看涨)",
                            "desc": f"中枢下方离开力度衰减(面积比{exit_area/max(entry_area,0.01):.2f})",
                        })

    summary_parts = []
    if result["trend_beichi"]:
        summary_parts.append(result["trend_beichi"])
    if result["range_beichi"]:
        summary_parts.append(f"{len(result['range_beichi'])}个中枢盘整背驰")
    if summary_parts:
        result["summary"] = "检测到" + "、".join(summary_parts)
    else:
        result["summary"] = "当前无明确背驰信号"

    return result


# ═══════════════════════════════════════════════════════════════
# 8. 三类买卖点识别
# ═══════════════════════════════════════════════════════════════

def chan_maidian(merged_bars, bi_list, zs_list, closes):
    """
    识别缠论三类买卖点。
    一买：离开最后一个中枢后的底背驰结束点
    二买：一买后不创新低的次低点
    三买：突破中枢后，回踩不落入中枢的点
    """
    if not zs_list or not bi_list or len(closes) < 20:
        return {"buy_points": [], "sell_points": [], "summary": "数据不足"}

    last_zs = zs_list[-1]
    last_close = closes[-1]
    last_idx = len(closes) - 1

    buy_points = []
    sell_points = []

    # ── 一买：离开中枢的底背驰段结束 ──
    # 条件：价格在中枢下方 + 下跌笔的结束点 + 出现底背驰
    if last_close < last_zs["zd"]:
        down_bis = [b for b in bi_list if b["direction"] == "down"]
        if down_bis:
            last_down = down_bis[-1]
            # 判断是否为背驰段结尾
            if last_down["end_idx"] >= last_idx - 5:
                buy_points.append({
                    "type": "一买",
                    "desc": f"离开中枢(ZD={last_zs['zd']})后底背驰结束",
                    "confidence": "中",
                })

    # ── 二买：一买后的次低点 ──
    if buy_points and any(bp["type"] == "一买" for bp in buy_points):
        # 查找一买发生后是否出现回调未破前低
        recent_lows = [min(b["low"] for b in bi_list[-3:])]
        if recent_lows and last_close > recent_lows[0] and last_close < last_zs["zd"]:
            buy_points.append({
                "type": "二买",
                "desc": f"回踩未破前低({recent_lows[0]}), 中枢下方",
                "confidence": "中",
            })

    # ── 三买：突破中枢后回踩不入 ──
    above_zs = closes[-1] > last_zs["zg"]
    recent_low = min(closes[-5:]) if len(closes) >= 5 else closes[-1]
    if above_zs and recent_low > last_zs["zd"]:
        # 判断是否有回踩动作：近期有低点接近中枢但不落入
        near_zs = any(last_zs["zg"] < c < last_zs["zg"] * 1.03 for c in closes[-10:])
        if near_zs:
            buy_points.append({
                "type": "三买",
                "desc": f"突破中枢上沿(ZG={last_zs['zg']})后回踩不落入",
                "confidence": "高" if last_close > last_zs["zg"] * 1.02 else "中",
            })

    # ── 卖点（对称逻辑） ──
    if last_close > last_zs["zg"]:
        up_bis = [b for b in bi_list if b["direction"] == "up"]
        if up_bis:
            last_up = up_bis[-1]
            if last_up["end_idx"] >= last_idx - 5:
                sell_points.append({
                    "type": "一卖",
                    "desc": f"离开中枢(ZG={last_zs['zg']})后顶背驰",
                    "confidence": "中",
                })

    summary_parts = []
    if buy_points:
        summary_parts.append(f"买点: {', '.join(bp['type'] for bp in buy_points)}")
    if sell_points:
        summary_parts.append(f"卖点: {', '.join(sp['type'] for sp in sell_points)}")
    summary = "; ".join(summary_parts) if summary_parts else "当前无明确缠论买卖点"

    return {
        "buy_points": buy_points,
        "sell_points": sell_points,
        "summary": summary,
    }


# ═══════════════════════════════════════════════════════════════
# 9. 顶层整合函数
# ═══════════════════════════════════════════════════════════════

def chan_full_analysis(records):
    """一次调用返回完整缠论分析结果。"""
    if len(records) < 30:
        return {"error": "K线数量不足(<30)，缠论分析不可靠", "valid": False}

    # 提取价格数据
    closes = [to_float(r.get("close")) for r in records if to_float(r.get("close")) > 0]

    if len(closes) < 30:
        return {"error": "有效K线不足", "valid": False}

    # 1. 包含处理
    merged = chan_merge_inclusions(records)
    merge_ratio = (len(records) - len(merged)) / len(records) * 100 if records else 0

    # 2. 分型
    fenxing = chan_fenxing(merged)
    top_fx = [f for f in fenxing if f["type"] == "顶"]
    bottom_fx = [f for f in fenxing if f["type"] == "底"]

    # 3. 笔
    bi_list = chan_bi(merged)
    up_bis = [b for b in bi_list if b["direction"] == "up"]
    down_bis = [b for b in bi_list if b["direction"] == "down"]

    # 4. 线段
    xd_list = chan_xianduan(bi_list)

    # 5. 中枢
    zs_list = chan_zhongshu(xd_list)

    # 6. 背驰
    beichi = chan_beichi(bi_list, zs_list, closes)

    # 7. 买卖点
    maidain = chan_maidian(merged, bi_list, zs_list, closes)

    # 8. 当前位置描述
    last_close = closes[-1]
    if zs_list:
        last_zs = zs_list[-1]
        if last_close > last_zs["zg"]:
            position = f"中枢上方({last_zs['zg']}之上)"
        elif last_close < last_zs["zd"]:
            position = f"中枢下方({last_zs['zd']}之下)"
        else:
            position = f"中枢内部(ZG={last_zs['zg']}, ZD={last_zs['zd']})"
    else:
        position = "无中枢，处于原始走势中"

    valid = len(bi_list) >= 3

    return {
        "valid": valid,
        "merged_count": len(merged),
        "original_count": len(records),
        "merge_ratio_pct": round(merge_ratio, 1),
        "fenxing_count": len(fenxing),
        "top_fenxing": len(top_fx),
        "bottom_fenxing": len(bottom_fx),
        "bi_count": len(bi_list),
        "up_bi": len(up_bis),
        "down_bi": len(down_bis),
        "xianduan_count": len(xd_list),
        "zhongshu_list": zs_list,
        "zhongshu_count": len(zs_list),
        "beichi": beichi,
        "maidian": maidain,
        "current_position": position,
    }


# ── 命令行快速测试 ──
if __name__ == "__main__":
    import sys
    import json
    from common import normalize_quote_code
    from kline import fetch as fetch_kline

    if len(sys.argv) < 2:
        print("用法: python3 chan.py <code>")
        sys.exit(1)

    code = normalize_quote_code(sys.argv[1])
    records = fetch_kline(code, 240, 250)
    result = chan_full_analysis(records)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
