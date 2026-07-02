"""
双针探底形态识别。
"""

from common import to_float


def detect_shuangzhen(records, closes, lows, volumes):
    """
    双针探底：5 日内两根长下影线触及相近价位 + 缩量。
    长下影标准：下影线 > 实体 × 2 或 > 上影线 × 3。
    """
    if len(records) < 5:
        return []

    results = []

    for i in range(5, len(records)):
        window = records[i - 5 : i + 1]
        lows[i - 5 : i + 1]
        w_vol = volumes[i - 5 : i + 1]

        # 找长下影线
        needle_days = []
        for j, r in enumerate(window):
            o, c, low, h = (
                to_float(r.get("open")),
                to_float(r.get("close")),
                to_float(r.get("low")),
                to_float(r.get("high")),
            )
            body = abs(c - o)
            lower = min(o, c) - low
            upper = h - max(o, c)
            if lower > body * 2 and lower > upper * 3 and body > 0:
                needle_days.append({"idx": i - 5 + j, "low": low, "shadow": lower})

        # 至少2根长下影，低点接近（<2% 差异）
        if len(needle_days) >= 2:
            for a in range(len(needle_days)):
                for b in range(a + 1, len(needle_days)):
                    na, nb = needle_days[a], needle_days[b]
                    if nb["idx"] - na["idx"] < 1:
                        continue
                    low_diff = abs(na["low"] - nb["low"]) / max(na["low"], 0.001) * 100
                    if low_diff < 2:
                        # 确认缩量
                        vol_needle = [volumes[na["idx"]], volumes[nb["idx"]]]
                        vol_others = [
                            v
                            for j, v in enumerate(w_vol)
                            if i - 5 + j not in (na["idx"], nb["idx"])
                        ]
                        if (
                            sum(vol_needle) / max(len(vol_needle), 1)
                            < sum(vol_others) / max(len(vol_others), 1) * 0.8
                        ):
                            results.append(
                                {
                                    "name": "双针探底",
                                    "type": "看涨",
                                    "date": records[nb["idx"]].get("day", ""),
                                    "desc": f"两低点{na['low']:.2f}/{nb['low']:.2f}差异{low_diff:.1f}%，缩量触底",
                                    "confidence": "高" if low_diff < 1 else "中",
                                    "idx": nb["idx"],
                                }
                            )

    return results
