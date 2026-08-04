"""均线止跌买点识别（第二类买点）。

策略逻辑：
- 条件A：股价不再新低 + 收盘站上 5 日线
- 条件B：回踩 20 日线不破（前期上升趋势中回踩支撑）

"不再新低"判断：回看期内最低点出现在左半段（已度过最低点），
配合收盘站上 MA5 且收盘回升确认止跌。

依赖: core (sma)
"""

from .core import _EPS, sma

_MA_STOP_LOOKBACK = 10  # 判断"不再新低"的回看周期
_MA5_PERIOD = 5
_MA20_PERIOD = 20
_MA20_TOLERANCE = 0.01  # 回踩 MA20 容差（±1%）
_MA20_BREACH = 0.98  # MA20 跌破阈值（最低价不低于 MA20*0.98）


def ma_stop_buy(closes, highs, lows, mas):
    """均线止跌买点（第二类买点）。

    Args:
        closes: 收盘价序列 list[float]
        highs: 最高价序列 list[float]（预留）
        lows: 最低价序列 list[float]
        mas: ma_system() 返回的 dict（含 ma5/ma20）

    Returns:
        dict: {"status": str, "signal": int, "desc": str, "type": str|None}
        signal: 1=止跌买点, 0=无信号
        type: "站上5日线"|"回踩20日线"|"双重止跌"|None
        数据不足时返回 None。
    """
    lookback = _MA_STOP_LOOKBACK
    if len(closes) < lookback + 1 or len(lows) < lookback + 1:
        return None

    ma5 = mas.get("ma5") if mas else None
    ma20 = mas.get("ma20") if mas else None

    # 如果 mas 没有预计算值，现场补算（保证轻量路径也能用）
    if ma5 is None:
        ma5 = sma(closes, _MA5_PERIOD)
    if ma20 is None:
        ma20 = sma(closes, _MA20_PERIOD)

    if ma5 is None or ma20 is None or ma20 < _EPS:
        return None

    today_close = closes[-1]
    prev_close = closes[-2]

    # ── 条件A：不再新低 + 收盘站上5日线 ──
    cond_a = False
    recent_lows = lows[-lookback:]
    min_idx = recent_lows.index(min(recent_lows))  # 最低点在回看期内的位置
    # 最低点在左半段 = 已度过最低点 = 不再新低
    no_new_low = min_idx < lookback // 2
    above_ma5 = today_close > ma5
    close_rebounding = today_close > prev_close
    if no_new_low and above_ma5 and close_rebounding:
        cond_a = True

    # ── 条件B：回踩20日线不破 ──
    cond_b = False
    near_ma20 = abs(today_close - ma20) / ma20 < _MA20_TOLERANCE
    not_broken = lows[-1] > ma20 * _MA20_BREACH
    uptrend = ma5 > ma20  # 前期上升趋势（短均线在长均线之上）
    if near_ma20 and not_broken and uptrend:
        cond_b = True

    if cond_a and cond_b:
        return {
            "status": "均线止跌(双重确认)",
            "signal": 1,
            "desc": f"不再新低+收盘{today_close:.2f}站上MA5({ma5:.2f})，同时回踩MA20({ma20:.2f})不破，双重止跌买点",
            "type": "双重止跌",
        }
    if cond_a:
        return {
            "status": "均线止跌(站上5日线)",
            "signal": 1,
            "desc": f"股价不再新低，收盘{today_close:.2f}站上MA5({ma5:.2f})，止跌买点",
            "type": "站上5日线",
        }
    if cond_b:
        return {
            "status": "均线止跌(回踩20日线)",
            "signal": 1,
            "desc": f"股价回踩MA20({ma20:.2f})不破，前期上升趋势(MA5>MA20)，支撑买点",
            "type": "回踩20日线",
        }

    return {
        "status": "无止跌信号",
        "signal": 0,
        "desc": "未满足均线止跌条件",
        "type": None,
    }
