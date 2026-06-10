"""笔的构建。"""
from .fenxing import chan_fenxing


def chan_bi(merged_bars):
    """
    从合并K线构建笔。
    相邻顶底分型之间至少要有1根独立K线（合并后）。
    """
    fenxing_list = chan_fenxing(merged_bars)
    bi_list = []

    if len(fenxing_list) < 2:
        return bi_list

    i = 0
    while i < len(fenxing_list) - 1:
        f0, f1 = fenxing_list[i], fenxing_list[i + 1]

        # 必须交替
        if f0["type"] == f1["type"]:
            i += 1
            continue

        # 至少1根独立K线间隔
        if f1["idx"] - f0["idx"] < 2:
            i += 1
            continue

        direction = "up" if f0["type"] == "底" else "down"
        bi_list.append({
            "start": f0,
            "end": f1,
            "direction": direction,
            "high": round(max(f0["bar"]["high"], f1["bar"]["high"]), 3),
            "low": round(min(f0["bar"]["low"], f1["bar"]["low"]), 3),
            "start_idx": f0["idx"],
            "end_idx": f1["idx"],
        })
        i += 1

    return bi_list
