"""顶底分型识别。"""


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
        if (
            b1["high"] > b0["high"]
            and b1["high"] > b2["high"]
            and b1["low"] > b0["low"]
            and b1["low"] > b2["low"]
        ):
            fenxing_list.append({"type": "顶", "bar": b1, "idx": i})

        # 底分型
        elif (
            b1["low"] < b0["low"]
            and b1["low"] < b2["low"]
            and b1["high"] < b0["high"]
            and b1["high"] < b2["high"]
        ):
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
