"""线段构建。"""


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
