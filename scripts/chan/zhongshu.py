"""中枢识别（笔中枢）。

v2.5.0 重构：中枢改由**笔**（而非线段）重叠构成——缠论笔中枢口径，
与下游 beichi/maidian 以 bi_list 定位进入/离开笔的操作层级一致。

原线段中枢的问题：日线上 250 根 K 线仅 2-4 个线段，中枢识别率极低；
且三线段重叠区可能覆盖巨幅走势（GG 与 ZG 相差数倍），中枢退化为
"全年区间"，位置/买卖点判断全部失真。

定义：连续 3 笔的价格重叠区间构成中枢，ZG = min(三笔高点)，
ZD = max(三笔低点)；后续笔与中枢区间 [ZD, ZG] 有重叠则中枢延伸，
首个完全离开的笔结束该中枢（GG/DD 随延伸笔更新）。
相邻中枢之间由离开/进入笔自然分隔，无需额外合并。
"""


def chan_zhongshu(bi_list):
    """
    从笔列表识别笔中枢。

    Returns:
        中枢列表（按时间升序），每个中枢含 zg/zd/mid/width/gg/dd 与
        bi_start/bi_end（bi_list 索引范围，含延伸笔）。
    """
    if len(bi_list) < 3:
        return []

    zs_list = []
    i = 0
    n = len(bi_list)
    while i <= n - 3:
        b0, b1, b2 = bi_list[i], bi_list[i + 1], bi_list[i + 2]

        zg = min(b0["high"], b1["high"], b2["high"])
        zd = max(b0["low"], b1["low"], b2["low"])

        if zd >= zg:
            # 前三笔无重叠 → 从下一笔重新尝试
            i += 1
            continue

        gg = max(b0["high"], b1["high"], b2["high"])
        dd = min(b0["low"], b1["low"], b2["low"])

        # 中枢延伸：后续笔与 [ZD, ZG] 有重叠则并入，直到完全离开
        j = i + 3
        while j < n:
            b = bi_list[j]
            if b["low"] <= zg and b["high"] >= zd:
                gg = max(gg, b["high"])
                dd = min(dd, b["low"])
                j += 1
            else:
                break

        zs_list.append(
            {
                "zg": round(zg, 3),
                "zd": round(zd, 3),
                "mid": round((zg + zd) / 2, 3),
                "width": round(zg - zd, 3),
                "gg": round(gg, 3),
                "dd": round(dd, 3),
                "bi_start": i,
                "bi_end": j - 1,
            }
        )
        # 下一个中枢从离开笔开始扫描（离开笔可能与后续笔构成新中枢）
        i = j

    return zs_list
