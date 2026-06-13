"""背驰检测。"""
from technical.core import _ema_series
from .area import _macd_area  # v1.3.2: was chan/macd.py


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
    # v1.3.2: dea_series 比 dif_series 短 8 元素（EMA 9 的 warmup），
    # 裁剪 dif_series 到 dea_series 长度以保持索引对齐。
    if len(dea_series) < len(dif_series):
        dif_series = dif_series[-len(dea_series):]

    result = {"trend_beichi": None, "range_beichi": [], "summary": ""}

    # ── 趋势背驰：以最后一个中枢为锚点 ──
    # 仅比较"中枢前最后一段"和"中枢后第一段"的 MACD 面积
    if zs_list:
        last_zs = zs_list[-1]
        xd_start = last_zs.get("xd_start", 0)
        xd_end = last_zs.get("xd_end", 0)

        # 中枢前最后一笔（进入段）
        entry_bi = None
        for bi in reversed(bi_list):
            if bi["end_idx"] <= xd_start:
                entry_bi = bi
                break

        # 中枢后第一笔（离开段）
        exit_bi = None
        for bi in bi_list:
            if bi["start_idx"] >= xd_end:
                exit_bi = bi
                break

        if entry_bi and exit_bi and entry_bi["direction"] == exit_bi["direction"]:
            e_start, e_end = entry_bi["start_idx"], entry_bi["end_idx"]
            x_start, x_end = exit_bi["start_idx"], exit_bi["end_idx"]

            if e_end < len(dif_series) and x_end < len(dif_series):
                entry_area = _macd_area(dif_series, dea_series,
                                        min(e_start, len(dif_series) - 1),
                                        min(e_end, len(dif_series) - 1))
                exit_area = _macd_area(dif_series, dea_series,
                                       min(x_start, len(dif_series) - 1),
                                       min(x_end, len(dif_series) - 1))

                if exit_area < entry_area:
                    if entry_bi["direction"] == "down" and exit_bi["low"] < entry_bi["low"]:
                        result["trend_beichi"] = "底背驰(看涨)"
                    elif entry_bi["direction"] == "up" and exit_bi["high"] > entry_bi["high"]:
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
