"""K线包含处理。"""
from common import to_float


def chan_merge_inclusions(records, max_merge=3):
    """
    K线包含关系处理：连续涨势取高高，跌势取低低。
    返回合并后的 K 线列表。

    Args:
        records: K 线数据列表
        max_merge: 最大连续合并次数（A 股涨跌停适配，默认 3，设为 0 表示不限制）
    """
    if len(records) < 3:
        return records

    bars = []
    for r in records:
        bars.append({
            "high": to_float(r.get("high")),
            "low": to_float(r.get("low")),
            "open": to_float(r.get("open")),
            "close": to_float(r.get("close")),
            "date": r.get("day", ""),
            "idx": len(bars),
        })

    merged = [dict(bars[0])]
    direction = "up"  # 默认向上
    consecutive_merges = 0

    for i in range(1, len(bars)):
        prev = merged[-1]
        curr = bars[i]

        # 检查包含关系：一根K线的高低范围完全包含另一根
        curr_in_prev = curr["high"] <= prev["high"] and curr["low"] >= prev["low"]
        prev_in_curr = prev["high"] <= curr["high"] and prev["low"] >= curr["low"]

        if (curr_in_prev or prev_in_curr) and (max_merge == 0 or consecutive_merges < max_merge):
            consecutive_merges += 1
            if direction == "up":
                merged[-1] = {
                    "high": max(prev["high"], curr["high"]),
                    "low": max(prev["low"], curr["low"]),
                    "date": curr["date"],
                    "idx": curr["idx"],
                }
            else:
                merged[-1] = {
                    "high": min(prev["high"], curr["high"]),
                    "low": min(prev["low"], curr["low"]),
                    "date": curr["date"],
                    "idx": curr["idx"],
                }
        else:
            consecutive_merges = 0
            # 更新方向
            if curr["high"] > prev["high"]:
                direction = "up"
            elif curr["low"] < prev["low"]:
                direction = "down"
            merged.append(dict(curr))

    return merged
