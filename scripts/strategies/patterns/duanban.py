"""断板反包形态识别。

策略逻辑：
涨停后断板（次日未涨停/回调），随后再次涨停反包，确认强势延续。

与"涨停双响炮"的区别：
- 双响炮要求中间缩量整理（不跌），重点在"蓄势再攻"
- 断板反包允许中间回调下跌，重点在"断板后重新收复"，反包创新高

买点：第一类买点的变体（突破一段箱体上沿/断板后新高）。
"""

from common import to_float, board_type as _board_type
from strategies.patterns.utils import _is_limit_up

_MAX_GAP = 5  # 两次涨停间隔最大天数
_BREAK_FLOOR_RATIO = 0.95  # 中间断板期收盘不得跌破首板实体下沿的 95%


def detect_duanban(records, closes, highs, lows, volumes, code=""):
    """断板反包：涨停->断板回调->再涨停反包。

    Args:
        records: KlineBar dict 列表（含 open/high/low/close/volume/day）
        closes/highs/lows/volumes: 并行价格序列
        code: 股票代码（用于判断板块涨跌幅限制）

    Returns:
        list[dict]: [{"name", "type", "date", "desc", "confidence", "idx", "metrics"}]
        name 固定 "断板反包"，type 固定 "看涨"。
    """
    if len(records) < 5:
        return []

    board = _board_type(code) if code else "主板"
    results = []

    for i in range(4, len(records)):
        r_now = records[i]
        o_now = to_float(r_now.get("open"))
        c_now = to_float(r_now.get("close"))
        v_now = to_float(r_now.get("volume"))
        prev_close_now = to_float(records[i - 1].get("close"))

        # 当天必须是涨停
        if not _is_limit_up(o_now, c_now, prev_close_now, board):
            continue

        # 回溯 1-5 日找前一个涨停日 zt1
        for gap in range(1, _MAX_GAP + 1):
            zt1_idx = i - gap - 1
            if zt1_idx < 0:
                break

            r_zt1 = records[zt1_idx]
            o1 = to_float(r_zt1.get("open"))
            c1 = to_float(r_zt1.get("close"))
            v1 = to_float(r_zt1.get("volume"))
            h1 = to_float(r_zt1.get("high"))
            prev_close_1 = (
                to_float(records[zt1_idx - 1].get("close")) if zt1_idx > 0 else c1
            )

            # 第一次涨停
            if not _is_limit_up(o1, c1, prev_close_1, board):
                continue

            # 中间至少有 1 日"断板"（非涨停）
            mid_range = range(zt1_idx + 1, i)
            mid_closes = [closes[k] for k in mid_range]
            has_break = any(
                not _is_limit_up(
                    to_float(records[k].get("open")),
                    to_float(records[k].get("close")),
                    to_float(records[k - 1].get("close")),
                    board,
                )
                for k in mid_range
            )
            if not has_break:
                continue  # 中间全是涨停 = 连板，不是断板反包

            # 中间断板期收盘不破首板实体下沿的 95%
            zt1_floor = min(o1, c1) * _BREAK_FLOOR_RATIO
            if mid_closes and min(mid_closes) < zt1_floor:
                continue  # 回调太深，不是健康反包

            # 反包创新高：今日收盘 > 首板涨停日最高价
            breakout_new_high = c_now > h1

            # 量能：今日放量 vs 中间日均量
            mid_volumes = [to_float(records[k].get("volume")) for k in mid_range]
            avg_mid_vol = sum(mid_volumes) / len(mid_volumes) if mid_volumes else v1
            vol_expansion = v_now > avg_mid_vol if avg_mid_vol > 0 else False

            # 置信度
            if breakout_new_high and vol_expansion:
                confidence = "高"
            elif breakout_new_high or vol_expansion:
                confidence = "中"
            else:
                continue  # 既没创新高也没放量，不构成有效反包

            metrics = {
                "gap": gap,
                "breakout_new_high": breakout_new_high,
                "vol_expansion": vol_expansion,
                "vol_ratio": round(v_now / avg_mid_vol, 2) if avg_mid_vol > 0 else 0,
            }

            results.append(
                {
                    "name": "断板反包",
                    "type": "看涨",
                    "date": r_now.get("day", ""),
                    "desc": (
                        f"首板{gap + 1}日前+{gap}日断板回调+今日再涨停"
                        f"{'反包创新高' if breakout_new_high else '收复前高'}"
                        f"{'(放量)' if vol_expansion else ''}"
                    ),
                    "confidence": confidence,
                    "idx": i,
                    "metrics": metrics,
                }
            )
            break  # 找到最近的 zt1 即可，不再往更早找

    return results
