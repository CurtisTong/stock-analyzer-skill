"""
底部首板形态识别。
"""

from common import to_float, board_type as _board_type
from strategies.patterns.utils import _is_limit_up, _is_bullish


def detect_dibu_shouban(records, closes, highs, lows, volumes, code=""):
    """
    底部首板：下跌趋势后首个涨停 → 2-3 日缩量回踩不破涨停日低点 → 确认。
    """
    if len(records) < 20:
        return []

    board = _board_type(code) if code else "主板"

    results = []

    for i in range(10, len(records) - 3):
        r_zt = records[i]
        o_zt, c_zt, h_zt, l_zt = [
            to_float(r_zt.get(k)) for k in ["open", "close", "high", "low"]
        ]
        v_zt = to_float(r_zt.get("volume"))
        prev_close = to_float(records[i - 1].get("close"))

        # 当天涨停
        if not _is_limit_up(o_zt, c_zt, prev_close, board):
            continue

        # 涨停前处于下跌趋势（过去10天最高价低于20天前的高点）
        recent_high = max(highs[i - 10 : i]) if i >= 10 else highs[i]
        older_high = max(highs[max(i - 20, 0) : i - 10]) if i >= 20 else recent_high
        if recent_high > older_high * 0.95:
            continue

        # 涨停前 5 天有过下跌
        pre_change = (
            (closes[i - 1] - closes[i - 5]) / max(closes[i - 5], 0.001) * 100
            if i >= 5
            else 0
        )
        if pre_change > -5:
            continue

        # 未来 2-3 日回踩：缩量 + 收盘不破涨停日低点
        backtest_ok = True
        min_vol = float("inf")
        for k in range(i + 1, min(i + 4, len(records))):
            if closes[k] < l_zt * 0.98:
                backtest_ok = False
                break
            min_vol = min(min_vol, volumes[k])

        if not backtest_ok:
            continue

        # 缩量确认（回踩期间均量 < 涨停日量 × 0.5）
        if min_vol < v_zt * 0.5:
            # 确认点：缩量后出现阳线
            for k in range(i + 1, min(i + 4, len(records))):
                rk = records[k]
                ok, ck = to_float(rk.get("open")), to_float(rk.get("close"))
                if _is_bullish(ok, ck) and volumes[k] > min_vol * 1.2:
                    results.append(
                        {
                            "name": "底部首板",
                            "type": "看涨",
                            "date": rk.get("day", ""),
                            "desc": f"下跌后首板+{k - i}日缩量回踩不破涨停低点{l_zt:.2f}",
                            "confidence": "高" if k - i <= 2 else "中",
                            "idx": k,
                        }
                    )
                    break

    return results
