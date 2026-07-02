"""
涨停双响炮形态识别。
"""

from common import to_float, board_type as _board_type
from strategies.patterns.utils import _is_limit_up


def detect_zhangting(records, closes, volumes, code=""):
    """
    涨停双响炮：涨停 → 1-3 日缩量整理 → 再次涨停放量。
    用于确认强势股的二次攻击信号。
    """
    if len(records) < 5:
        return []

    board = _board_type(code) if code else "主板"

    results = []

    for i in range(4, len(records)):
        r_now = records[i]
        o_now, c_now, v_now = (
            to_float(r_now.get("open")),
            to_float(r_now.get("close")),
            to_float(r_now.get("volume")),
        )

        # 当天必须是涨停
        prev_close_now = to_float(records[i - 1].get("close"))
        if not _is_limit_up(o_now, c_now, prev_close_now, board):
            continue

        # 回溯 1-3 天整理
        for gap in range(1, 4):
            zt1_idx = i - gap - 1
            if zt1_idx < 0:
                continue

            r_zt1 = records[zt1_idx]
            o1, c1, v1 = (
                to_float(r_zt1.get("open")),
                to_float(r_zt1.get("close")),
                to_float(r_zt1.get("volume")),
            )
            prev_close_1 = (
                to_float(records[zt1_idx - 1].get("close")) if zt1_idx > 0 else c1
            )

            # 第一次涨停
            if not _is_limit_up(o1, c1, prev_close_1, board):
                continue

            # 中间整理期：缩量 + 收盘不破第一次涨停实体中点
            zt1_mid = (o1 + c1) / 2
            consolidation_ok = True
            for k in range(zt1_idx + 1, i):
                vk = volumes[k]
                ck = closes[k]
                if vk > v1 * 0.6 or ck < zt1_mid:
                    consolidation_ok = False
                    break

            if not consolidation_ok:
                continue

            # 第二次涨停比第一次放量
            if v_now > v1 * 1.2:
                results.append(
                    {
                        "name": "涨停双响炮",
                        "type": "看涨",
                        "date": r_now.get("day", ""),
                        "desc": f"首板{gap + 1}日前+{gap}日缩量整理+今日再封板放量",
                        "confidence": "高" if gap == 1 and v_now > v1 * 1.5 else "中",
                        "idx": i,
                    }
                )
                break

    return results
