"""笔的构建。"""

from .fenxing import chan_fenxing


def chan_bi(merged_bars):
    """
    从合并K线构建笔。
    相邻顶底分型之间至少要有1根独立K线（合并后）。
    同类型连续分型保留更强的（顶保留更高的，底保留更低的），继续向后寻找异类型配对。
    """
    fenxing_list = chan_fenxing(merged_bars)
    bi_list = []

    if len(fenxing_list) < 2:
        return bi_list

    # 第一步：同类型连续分型合并，保留更强的
    merged_fenxing = [fenxing_list[0]]
    for fx in fenxing_list[1:]:
        last = merged_fenxing[-1]
        if fx["type"] == last["type"]:
            # 同类型：顶保留更高的，底保留更低的
            if fx["type"] == "顶" and fx["bar"]["high"] > last["bar"]["high"]:
                merged_fenxing[-1] = fx
            elif fx["type"] == "底" and fx["bar"]["low"] < last["bar"]["low"]:
                merged_fenxing[-1] = fx
            # 否则保留 last（更强的那个），跳过当前较弱的
        else:
            merged_fenxing.append(fx)

    # 第二步：从合并后的分型列表构建笔
    i = 0
    while i < len(merged_fenxing) - 1:
        f0, f1 = merged_fenxing[i], merged_fenxing[i + 1]

        # 至少1根独立K线间隔
        if f1["idx"] - f0["idx"] < 2:
            i += 1
            continue

        direction = "up" if f0["type"] == "底" else "down"
        bi_list.append(
            {
                "start": f0,
                "end": f1,
                "direction": direction,
                "high": round(max(f0["bar"]["high"], f1["bar"]["high"]), 3),
                "low": round(min(f0["bar"]["low"], f1["bar"]["low"]), 3),
                "start_idx": f0["idx"],
                "end_idx": f1["idx"],
            }
        )
        i += 1

    return bi_list
