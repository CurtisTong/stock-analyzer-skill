"""背驰检测。"""

from technical.core import aligned_macd
from .area import _macd_area  # v1.3.2: was chan/macd.py


def chan_beichi(bi_list, zs_list, closes, date_to_close_idx=None, range_tolerance=0.8):
    """
    背驰检测。
    趋势背驰：比较两段同向走势的 MACD 面积，面积衰减+价格创极端=背驰。
    盘整背驰：比较中枢前后两段的力度。

    Args:
        range_tolerance: 盘整背驰容差阈值（默认 0.8，即面积比 < 80% 视为背驰）

    Args:
        date_to_close_idx: {date: closes_index} 映射，用于将 bi 的 merged 坐标系
            idx 正确映射到 closes 坐标系（P2-C3 修复：原直接减 _dea_offset 因
            bi idx 是 merged 空间而非 closes 空间，会导致面积计算错位）。
    """
    if len(closes) < 34 or len(bi_list) < 4:
        return {"trend_beichi": None, "range_beichi": [], "summary": "数据不足"}

    def _mapped_idx(bi, key):
        """将 bi 的 merged idx 通过 date 映射到 closes idx；映射失败回退原值。"""
        merged_idx = bi[key] if key in bi else None
        # bi 的 start/end 是 fenxing dict，含 bar.date
        fx = bi.get("start") if key == "start_idx" else bi.get("end")
        bar = fx.get("bar", {}) if fx else {}
        d = bar.get("date", "")
        if date_to_close_idx and d and d in date_to_close_idx:
            return date_to_close_idx[d]
        return merged_idx

    # 计算 DIF/DEA 序列（统一使用 aligned_macd 接口）
    macd_data = aligned_macd(closes)
    dif_series = macd_data["dif_series"]
    dea_series = macd_data["dea_series"]
    _dea_offset = macd_data["dea_offset"]

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
            # P2-C3: bi idx 是 merged 坐标系，通过 date 映射到 closes 坐标系，
            # 再减 _dea_offset 映射到 trim 后的 dif_series
            e_start = _mapped_idx(entry_bi, "start_idx") - _dea_offset
            e_end = _mapped_idx(entry_bi, "end_idx") - _dea_offset
            x_start = _mapped_idx(exit_bi, "start_idx") - _dea_offset
            x_end = _mapped_idx(exit_bi, "end_idx") - _dea_offset

            if (
                0 <= e_start
                and e_end < len(dif_series)
                and 0 <= x_start
                and x_end < len(dif_series)
            ):
                entry_area = _macd_area(dif_series, dea_series, e_start, e_end)
                exit_area = _macd_area(dif_series, dea_series, x_start, x_end)

                if exit_area < entry_area:
                    if (
                        entry_bi["direction"] == "down"
                        and exit_bi["low"] < entry_bi["low"]
                    ):
                        result["trend_beichi"] = "底背驰(看涨)"
                    elif (
                        entry_bi["direction"] == "up"
                        and exit_bi["high"] > entry_bi["high"]
                    ):
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
            # P2-C3: 通过 date 映射坐标系
            e_start = _mapped_idx(entry_bi, "start_idx") - _dea_offset
            e_end = _mapped_idx(entry_bi, "end_idx") - _dea_offset
            x_start = _mapped_idx(exit_bi, "start_idx") - _dea_offset
            x_end = _mapped_idx(exit_bi, "end_idx") - _dea_offset

            if (
                0 <= e_start
                and e_end < len(dif_series)
                and 0 <= x_start
                and x_end < len(dif_series)
            ):
                entry_area = _macd_area(dif_series, dea_series, e_start, e_end)
                exit_area = _macd_area(dif_series, dea_series, x_start, x_end)

                # 离开段面积 < 进入段面积 * 容差阈值 = 盘整背驰
                # v2.4.0: 容差阈值从函数参数读取，默认 0.8（允许 20% 容差）
                range_tolerance_local = range_tolerance
                if exit_area < entry_area * range_tolerance_local:
                    zs.get("mid", 0)
                    last_close = closes[-1]
                    if last_close > zs.get("zg", 0):
                        result["range_beichi"].append(
                            {
                                "zs_idx": zs_idx,
                                "type": "盘整背驰(看跌)",
                                "desc": f"中枢上方离开力度衰减(面积比{exit_area/max(entry_area, 0.01):.2f})",
                            }
                        )
                    elif last_close < zs.get("zd", 0):
                        result["range_beichi"].append(
                            {
                                "zs_idx": zs_idx,
                                "type": "盘整背驰(看涨)",
                                "desc": f"中枢下方离开力度衰减(面积比{exit_area/max(entry_area, 0.01):.2f})",
                            }
                        )

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
