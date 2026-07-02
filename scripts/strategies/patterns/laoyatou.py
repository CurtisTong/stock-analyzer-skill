"""
老鸭头形态识别。
"""


def detect_laoyatou(records, closes, volumes, mas):
    """
    老鸭头形态：三阶段（鸭颈 → 鸭头 → 鸭嘴）。
    鸭颈：MA5 > MA10 > MA20，股价沿MA5上行
    鸭头：MA5下穿MA10形成凹坑，股价回调但未跌破MA60
    鸭嘴：MA5重新上穿MA10，放量突破前高
    """
    if (
        len(closes) < 60
        or "ma5" not in mas
        or "ma10" not in mas
        or "ma20" not in mas
        or "ma60" not in mas
    ):
        return []

    ma5, ma10, ma20, ma60 = mas["ma5"], mas["ma10"], mas["ma20"], mas["ma60"]

    # 最小长度
    if len(ma60) < 20:
        return []

    # 统一用 ma60 长度作为基准（最短的 MA），对齐索引
    # ma60 对应 closes[59:], ma20 对应 closes[19:]
    # 在 ma60 索引空间工作，closes 偏移 = 59
    cl_offset = len(closes) - len(ma60)
    ma5_offset = len(ma5) - len(ma60)
    ma10_offset = len(ma10) - len(ma60)
    ma20_offset = len(ma20) - len(ma60)

    results = []

    # 扫描鸭嘴形成点（MA5 刚上穿 MA10），从 ma60 空间找
    for i_ma60 in range(20, len(ma60)):
        i5 = i_ma60 + ma5_offset
        i10 = i_ma60 + ma10_offset
        ci = i_ma60 + cl_offset

        if i5 < 1 or ci >= len(closes):
            continue

        # MA5 刚金叉 MA10
        if not (ma5[i5 - 1] <= ma10[i10 - 1] and ma5[i5] > ma10[i10]):
            continue

        # 回溯找鸭头：前 5-15 天内 MA5/10 下穿点
        duck_head_j = None
        for j_ma60 in range(max(i_ma60 - 15, 5), i_ma60 - 2):
            j5 = j_ma60 + ma5_offset
            j10 = j_ma60 + ma10_offset
            if j5 < 1:
                continue
            if ma5[j5] < ma10[j10] and ma5[j5] < ma5[j5 - 1]:
                # 确保鸭头时股价在 MA60 上方
                j_ci = j_ma60 + cl_offset
                if closes[j_ci] > ma60[j_ma60] * 0.95:
                    duck_head_j = j_ma60
                    break

        if duck_head_j is None:
            continue

        # 验证鸭颈：鸭头之前的上升趋势（MA5 > MA10 > MA20 至少3天）
        neck_days = 0
        for k_ma60 in range(max(duck_head_j - 10, 0), duck_head_j - 1):
            k5 = k_ma60 + ma5_offset
            k10 = k_ma60 + ma10_offset
            k20 = k_ma60 + ma20_offset
            if k20 >= 0 and k5 < len(ma5) and k20 < len(ma20):
                if ma5[k5] > ma10[k10] > ma20[k20]:
                    neck_days += 1

        if neck_days < 3:
            continue

        # 验证鸭嘴：放量 + 突破前高
        head_ci = duck_head_j + cl_offset
        lookback = min(head_ci, 10)
        prev_high = (
            max(closes[head_ci - lookback : head_ci])
            if lookback >= 1
            else closes[head_ci]
        )

        vol_recent = [volumes[k] for k in range(max(ci - 3, 0), ci + 1)]
        vol_older = [volumes[k] for k in range(max(head_ci - 3, 0), head_ci + 1)]
        avg_recent = sum(vol_recent) / max(len(vol_recent), 1)
        avg_older = sum(vol_older) / max(len(vol_older), 1)
        vol_expanding = avg_recent > avg_older * 1.2

        breakout = closes[ci] > prev_high * 1.02

        if vol_expanding and breakout:
            confidence = "高" if closes[ci] > prev_high * 1.05 else "中"
            results.append(
                {
                    "name": "老鸭头",
                    "type": "看涨",
                    "date": records[ci].get("day", ""),
                    "desc": f"鸭嘴确认：MA5重上MA10+放量突破前高{prev_high:.2f}",
                    "confidence": confidence,
                    "idx": ci,
                }
            )

    return results
