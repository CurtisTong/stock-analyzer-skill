"""线段构建。

v2.4.0 增强：加入特征序列分析（feature sequence）。
缠论原文定义：线段破坏分为两种情况--
1. 上升段：从高点开始的下跌笔跌破特征序列分型最低点
2. 下降段：从低点开始的上涨笔突破特征序列分型最高点

特征序列 = 线段内除起点笔外的**反向笔**的极值序列：
- 上升段：取下跌笔的低点（low）
- 下降段：取上涨笔的高点（high）
"""


def _feature_sequence_break(seg_bis: list, direction: str, new_bi: dict) -> bool:
    """特征序列破坏判断（v2.4.0 增强）。

    Args:
        seg_bis: 当前线段包含的笔列表
        direction: "up" 上升段 / "down" 下降段
        new_bi: 新加入的笔

    Returns:
        True 表示线段被破坏，应结束当前线段
    """
    if len(seg_bis) < 3:
        return False

    # 特征序列 = 除起点笔外的反向笔（缠论标准）
    # 上升段的特征序列 = 下跌笔的低点；下降段 = 上涨笔的高点
    rest_bis = seg_bis[1:]  # 排除起点笔
    if direction == "up":
        feature_lows = [b["low"] for b in rest_bis if b["direction"] == "down"]
        if not feature_lows:
            return False
        # 上升段被破坏：新笔的 low 跌破特征序列最低点
        return new_bi.get("low", float("inf")) < min(feature_lows)
    else:
        feature_highs = [b["high"] for b in rest_bis if b["direction"] == "up"]
        if not feature_highs:
            return False
        # 下降段被破坏：新笔的 high 突破特征序列最高点
        return new_bi.get("high", float("-inf")) > max(feature_highs)


def chan_xianduan(bi_list, use_feature_seq: bool = True):
    """
    从笔构建线段。

    Args:
        bi_list: 笔列表
        use_feature_seq: v2.4.0 新增——是否启用特征序列破坏判断（默认 True）
            启用后线段破坏判断更严格，符合缠论原文定义

    Returns:
        线段列表
    """
    if len(bi_list) < 3:
        return []

    xd_list = []
    i = 0
    while i <= len(bi_list) - 3:
        b0, b1, b2 = bi_list[i], bi_list[i + 1], bi_list[i + 2]

        # 前三笔必须有重叠
        overlap_high = min(b0["high"], b1["high"], b2["high"])
        overlap_low = max(b0["low"], b1["low"], b2["low"])

        if overlap_low >= overlap_high:
            i += 1
            continue

        # 线段方向 = 第一笔方向
        direction = b0["direction"]

        # 固定参考点：线段起点的极值（不随后续笔更新）
        if direction == "up":
            seg_start_low = b0["low"]
        else:
            seg_start_high = b0["high"]

        # 扩展线段：加入更多笔
        j = i + 3
        while j < len(bi_list):
            next_bi = bi_list[j]
            seg_bis = bi_list[i:j]
            broken = False

            if use_feature_seq and len(seg_bis) >= 3:
                # v2.4.0：特征序列破坏判断（更严格，符合缠论原文）
                broken = _feature_sequence_break(seg_bis, direction, next_bi)
            elif direction == "up":
                # 简化判断：后续笔的 low 不能跌破线段起点的 low
                broken = next_bi["low"] < seg_start_low
            else:
                broken = next_bi["high"] > seg_start_high

            if not broken:
                j += 1
            else:
                break

        seg_bis = bi_list[i:j]
        xd_list.append(
            {
                "direction": direction,
                "bi_count": len(seg_bis),
                "start_bi": i,
                "end_bi": j - 1,
                "high": round(max(b["high"] for b in seg_bis), 3),
                "low": round(min(b["low"] for b in seg_bis), 3),
                "feature_seq_used": use_feature_seq,
            }
        )
        i = j

    return xd_list
