"""
美人肩形态识别。
"""


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
        price_high = (
            max(highs[j] for j in consolidation_range)
            if consolidation_range
            else closes[ci]
        )
        price_low = (
            min(lows[j] for j in consolidation_range)
            if consolidation_range
            else closes[ci]
        )
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
        if (
            sum(consol_vol) / len(consol_vol)
            > sum(pre_vol) / max(len(pre_vol), 1) * 0.7
        ):
            continue

        # 条件4：今日放量突破横盘区间
        if (
            volumes[ci] > sum(consol_vol) / len(consol_vol) * 1.5
            and closes[ci] > price_high
        ):
            results.append(
                {
                    "name": "美人肩",
                    "type": "看涨",
                    "date": records[ci].get("day", ""),
                    "desc": f"横盘{len(consolidation_range)}日振幅{amplitude:.1f}%不破MA10后放量突破",
                    "confidence": (
                        "高"
                        if volumes[ci] > sum(consol_vol) / len(consol_vol) * 2
                        else "中"
                    ),
                    "idx": ci,
                }
            )

    return results
