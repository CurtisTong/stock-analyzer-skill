"""中枢识别。"""


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

        # 两两重叠校验：每对线段必须有共同区间
        if not (
            max(x0["low"], x1["low"]) < min(x0["high"], x1["high"])
            and max(x1["low"], x2["low"]) < min(x1["high"], x2["high"])
            and max(x0["low"], x2["low"]) < min(x0["high"], x2["high"])
        ):
            continue

        zg = min(x0["high"], x1["high"], x2["high"])
        zd = max(x0["low"], x1["low"], x2["low"])

        if zd < zg:
            zs_list.append(
                {
                    "zg": round(zg, 3),
                    "zd": round(zd, 3),
                    "mid": round((zg + zd) / 2, 3),
                    "width": round(zg - zd, 3),
                    "xd_start": i,
                    "xd_end": i + 2,
                    # bi_list 索引范围：供 beichi.py 直接定位进入/离开笔，
                    # 避免将 xd_list 索引误当作 merged-bar 索引比较
                    "bi_start": xd_list[i]["start_bi"],
                    "bi_end": xd_list[i + 2]["end_bi"],
                }
            )

    # 合并重叠中枢
    if len(zs_list) <= 1:
        return zs_list

    merged_zs = [zs_list[0]]
    for zs in zs_list[1:]:
        last = merged_zs[-1]
        # 有重叠（新中枢的低点 < 旧中枢的高点）且线段索引连续
        index_continuous = zs["xd_start"] <= last["xd_end"] + 1
        if zs["zd"] < last["zg"] and zs["zg"] > last["zd"] and index_continuous:
            # 交集：取较低的高点、较高的低点，与初始构建（zg=min, zd=max）一致
            # 缠论中枢合并应保持交集而非并集（并集会扩大中枢范围，违反定义）
            new_zg = min(last["zg"], zs["zg"])
            new_zd = max(last["zd"], zs["zd"])
            merged_zs[-1] = {
                "zg": round(new_zg, 3),
                "zd": round(new_zd, 3),
                "mid": round((new_zg + new_zd) / 2, 3),
                "width": round(new_zg - new_zd, 3),
                "xd_start": last["xd_start"],
                "xd_end": zs["xd_end"],
                "bi_start": last["bi_start"],
                "bi_end": zs["bi_end"],
            }
        else:
            merged_zs.append(zs)

    return merged_zs
