"""线段构建。

v2.5.0 重构：特征序列破坏判定从"新笔突破特征序列全局极值"改为
"特征序列包含处理 + 分型 + 跌破分型区间确认"（缠论第 67/71 课口径）。

原全局极值判定的问题：只要回调笔不破全局前低，线段就一直延续——
250 根日 K 只能划出 2-3 个线段（一段 40 笔），中枢与背驰检测连锁失效。
新判定：上升线段中，反向笔（向下笔）构成特征序列，特征序列出现顶分型
后，若后续向下笔跌破分型区间低点，则线段结束于分型中间元素的前一笔
（即线段终点 = 分型中间元素的高点 = 线段最高点）。

仍保留的简化（与标准差异，输出可能与标准缠论软件不同）：
- 不区分第一种/第二种情况（分型元素间有无缺口）：统一按第一种情况处理，
  即分型成立 + 跌破确认即结束，缺口情形不再要求反向特征序列分型二次确认。
  该口径偏严格，线段偏短。
"""


def _find_segment_end(bi_list, start, direction):
    """特征序列法：返回线段最后一笔的索引（含 start，至少 start+2）。

    上升段：特征序列 = 线段内向下笔的 (high, low)，按跌势做包含处理（低低）；
    出现顶分型（中间元素 high 最高）后，后续向下笔跌破分型区间低点 → 确认结束。
    下降段镜像：特征序列 = 向上笔按涨势包含处理（高高），底分型 + 突破确认。
    """
    n = len(bi_list)
    feature_seq = []  # 处理后的特征序列元素：{"high", "low", "bi"}（bi=该元素对应的最近反向笔索引）
    for j in range(start + 1, n):
        b = bi_list[j]
        if b["direction"] == direction:
            continue
        elem = {"high": b["high"], "low": b["low"], "bi": j}
        if feature_seq:
            last = feature_seq[-1]
            contained = (elem["high"] <= last["high"] and elem["low"] >= last["low"]) or (
                last["high"] <= elem["high"] and last["low"] >= elem["low"]
            )
            if contained:
                # 包含处理方向与线段方向相反：上升段按跌势（低低），下降段按涨势（高高）
                if direction == "up":
                    elem = {
                        "high": min(last["high"], elem["high"]),
                        "low": min(last["low"], elem["low"]),
                        "bi": j,
                    }
                else:
                    elem = {
                        "high": max(last["high"], elem["high"]),
                        "low": max(last["low"], elem["low"]),
                        "bi": j,
                    }
                feature_seq[-1] = elem
            else:
                feature_seq.append(elem)
        else:
            feature_seq.append(elem)

        # 检查特征序列分型（处理后的最近 3 元素）
        if len(feature_seq) >= 3:
            s1, s2, s3 = feature_seq[-3], feature_seq[-2], feature_seq[-1]
            if direction == "up" and s2["high"] > s1["high"] and s2["high"] > s3["high"]:
                # 顶分型：分型中间元素的起点即线段最高点候选
                pivot_low = min(s1["low"], s2["low"], s3["low"])
                for k in range(j + 1, n):
                    if bi_list[k]["direction"] == "down" and bi_list[k]["low"] < pivot_low:
                        return s2["bi"] - 1  # 线段终点 = 分型中间元素前一笔（同向笔）
            elif direction == "down" and s2["low"] < s1["low"] and s2["low"] < s3["low"]:
                pivot_high = max(s1["high"], s2["high"], s3["high"])
                for k in range(j + 1, n):
                    if bi_list[k]["direction"] == "up" and bi_list[k]["high"] > pivot_high:
                        return s2["bi"] - 1
    return n - 1  # 未确认破坏，线段延伸至末尾


def chan_xianduan(bi_list, use_feature_seq: bool = True):
    """
    从笔构建线段。

    Args:
        bi_list: 笔列表
        use_feature_seq: 是否启用特征序列分型破坏判断（默认 True）。
            False 时退化为简化判断：后续笔跌破线段起点极值即破坏（更宽松）。

    Returns:
        线段列表：{"direction", "bi_count", "start_bi", "end_bi", "high", "low",
        "feature_seq_used"}
    """
    if len(bi_list) < 3:
        return []

    xd_list = []
    i = 0
    n = len(bi_list)
    while i <= n - 3:
        b0, b1, b2 = bi_list[i], bi_list[i + 1], bi_list[i + 2]

        # 前三笔必须有重叠
        overlap_high = min(b0["high"], b1["high"], b2["high"])
        overlap_low = max(b0["low"], b1["low"], b2["low"])

        if overlap_low >= overlap_high:
            i += 1
            continue

        direction = b0["direction"]
        if use_feature_seq:
            end = _find_segment_end(bi_list, i, direction)
        else:
            # 简化判断：后续笔跌破/突破线段起点极值即破坏
            seg_start_low = b0["low"] if direction == "up" else None
            seg_start_high = b0["high"] if direction == "down" else None
            end = n - 1
            for j in range(i + 3, n):
                nxt = bi_list[j]
                if direction == "up" and nxt["low"] < seg_start_low:
                    end = j - 1
                    break
                if direction == "down" and nxt["high"] > seg_start_high:
                    end = j - 1
                    break

        seg_bis = bi_list[i : end + 1]
        xd_list.append(
            {
                "direction": direction,
                "bi_count": len(seg_bis),
                "start_bi": i,
                "end_bi": end,
                "high": round(max(b["high"] for b in seg_bis), 3),
                "low": round(min(b["low"] for b in seg_bis), 3),
                "feature_seq_used": use_feature_seq,
            }
        )
        i = end + 1

    return xd_list
