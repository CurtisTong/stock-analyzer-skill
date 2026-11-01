"""背驰检测。"""

from typing import Any

from technical.core import aligned_macd
from .area import _macd_area  # v1.3.2: was chan/macd.py


def chan_beichi(bi_list, zs_list, closes, date_to_close_idx=None, range_tolerance=0.8):
    """
    背驰检测。
    趋势背驰：比较两段同向走势的 MACD 面积，面积衰减+价格创极端=背驰。
    盘整背驰：比较中枢前后两段的力度。

    Args:
        date_to_close_idx: {date: closes_index} 映射，用于将 bi 的 merged 坐标系
            idx 正确映射到 closes 坐标系（P2-C3 修复：原直接减 _dea_offset 因
            bi idx 是 merged 空间而非 closes 空间，会导致面积计算错位）。
            映射失败的笔直接跳过背驰判断（诚实降级），不再回退到
            "把 merged 列表位置当 closes 索引"的错位坐标系。
        range_tolerance: 盘整背驰容差阈值（默认 0.8，即面积比 < 80% 视为背驰）
    """
    if len(closes) < 34 or len(bi_list) < 4:
        return {"trend_beichi": None, "range_beichi": [], "summary": "数据不足"}

    def _mapped_idx(bi, key):
        """将 bi 端点的 merged idx 通过 date 映射到 closes 索引；失败返回 None。"""
        fx = bi.get("start") if key == "start_idx" else bi.get("end")
        bar = fx.get("bar", {}) if fx else {}
        d = bar.get("date", "")
        if date_to_close_idx and d:
            return date_to_close_idx.get(d)
        return None

    # 计算 DIF/DEA 序列（统一使用 aligned_macd 接口）
    macd_data = aligned_macd(closes)
    dif_series = macd_data["dif_series"]
    dea_series = macd_data["dea_series"]
    _dea_offset = macd_data["dea_offset"]

    def _segment_area(bi, side):
        """单笔区间的同色 MACD 柱面积；任一端点映射失败返回 None。"""
        s = _mapped_idx(bi, "start_idx")
        e = _mapped_idx(bi, "end_idx")
        if s is None or e is None:
            return None
        s, e = s - _dea_offset, e - _dea_offset
        if not (0 <= s and e < len(dif_series)):
            return None
        # 同向走势比同色柱：上涨笔比红柱，下跌笔比绿柱
        return _macd_area(dif_series, dea_series, s, e, side=side)

    result: dict[str, Any] = {
        "trend_beichi": None,
        "range_beichi": [],
        "summary": "",
    }

    # ── 趋势背驰：以最后一个中枢为锚点 ──
    # 仅比较"中枢前最后一段"和"中枢后第一段"的 MACD 面积
    if zs_list:
        last_zs = zs_list[-1]
        # 使用 bi_list 索引（bi_start/bi_end）定位进入/离开笔，
        # 而非 xd_list 索引（xd_start/xd_end）--后者与 bi 的 merged-bar 索引不同坐标系
        bi_start = last_zs.get("bi_start", 0)
        bi_end = last_zs.get("bi_end", len(bi_list) - 1)

        # 中枢前最后一笔（进入段）：紧邻中枢第一笔之前的笔
        entry_bi = bi_list[bi_start - 1] if bi_start > 0 else None

        # 中枢后第一笔（离开段）：紧邻中枢最后一笔之后的笔
        exit_bi = bi_list[bi_end + 1] if bi_end + 1 < len(bi_list) else None

        if entry_bi and exit_bi and entry_bi["direction"] == exit_bi["direction"]:
            side = entry_bi["direction"]
            entry_area = _segment_area(entry_bi, side)
            exit_area = _segment_area(exit_bi, side)

            if entry_area is not None and exit_area is not None and entry_area > 0 and exit_area < entry_area:
                if side == "down" and exit_bi["low"] < entry_bi["low"]:
                    result["trend_beichi"] = "底背驰(看涨)"
                elif side == "up" and exit_bi["high"] > entry_bi["high"]:
                    result["trend_beichi"] = "顶背驰(看跌)"

    # ── 盘整背驰：检查每个中枢的进入段 vs 离开段 ──
    for zs_idx, zs in enumerate(zs_list):
        # 盘整背驰：中枢前后各有一段同向走势，比较 MACD 面积
        # 进入段 = 中枢前最后一笔（在中枢 bi_start 之前）
        # 离开段 = 中枢后第一笔（在中枢 bi_end 之后）
        # 看涨/看跌由离开段方向决定（离开段向下+力度衰减=看涨，反之看跌），
        # 不用当前价对比中枢区间——对老中枢而言当前价无时点意义。
        bi_start = zs.get("bi_start", 0)
        bi_end = zs.get("bi_end", len(bi_list) - 1)

        entry_bi = bi_list[bi_start - 1] if bi_start > 0 else None
        exit_bi = bi_list[bi_end + 1] if bi_end + 1 < len(bi_list) else None

        if entry_bi and exit_bi and entry_bi["direction"] == exit_bi["direction"]:
            side = entry_bi["direction"]
            entry_area = _segment_area(entry_bi, side)
            exit_area = _segment_area(exit_bi, side)

            if entry_area is None or exit_area is None:
                continue

            # 力度比较的前提：两侧都要有可比的同色动能。
            # - 进入段面积 0 → 该段无同色动能柱，无法判断力度；
            # - 离开段面积 0 → 离开段动能耗尽/未展开该色（实测宝丰出现"面积比0.00"），
            #   这是"没有动能"而非"力度衰减"，不构成背驰。
            # 二者若不排除，会把几乎任意中枢判成盘整背驰并连锁触发一买。
            if entry_area <= 0 or exit_area <= 0:
                continue

            # 离开段面积 < 进入段面积 * 容差阈值 = 盘整背驰
            # v2.4.0: 容差阈值从函数参数读取，默认 0.8（允许 20% 容差）
            if exit_area < entry_area * range_tolerance:
                if side == "up":
                    result["range_beichi"].append(
                        {
                            "zs_idx": zs_idx,
                            "type": "盘整背驰(看跌)",
                            "desc": f"中枢[{zs.get('zd', '?')}-{zs.get('zg', '?')}]向上离开力度衰减(面积比{exit_area/max(entry_area, 0.01):.2f})",
                        }
                    )
                else:
                    result["range_beichi"].append(
                        {
                            "zs_idx": zs_idx,
                            "type": "盘整背驰(看涨)",
                            "desc": f"中枢[{zs.get('zd', '?')}-{zs.get('zg', '?')}]向下离开力度衰减(面积比{exit_area/max(entry_area, 0.01):.2f})",
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
