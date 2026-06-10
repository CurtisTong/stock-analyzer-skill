"""背驰检测。"""
from technical.core import _ema_series
from .macd import _macd_area


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
