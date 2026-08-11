"""
成交量分析（量价配合、OBV）。
依赖: core (_find_swing_points)

P2-26: 量价状态枚举标准化 (VOLUME_PRICE_*)。所有调用方应使用枚举常量，
不再依赖魔法数字或散落的中文字符串。
"""

import statistics

from .core import _find_swing_points

# ---------- 量价状态枚举（P2-26 新增）----------
# signal: -1 负面 / 0 中性 / +1 正面
# 状态码: VP_RISE_VOL=1 放量上涨, VP_FALL_SHRINK=2 缩量下跌,
#         VP_RISE_SHRINK=3 缩量上涨(背离), VP_FALL_VOL=4 放量下跌(出货),
#         VP_NEUTRAL=0 量价中性
VP_RISE_VOL = 1  # 放量上涨（资金介入）
VP_FALL_SHRINK = 2  # 缩量下跌（抛压减轻）
VP_RISE_SHRINK = 3  # 缩量上涨（量价背离/弱势）
VP_FALL_VOL = 4  # 放量下跌（主力出货）
VP_NEUTRAL = 0  # 量价中性

# 状态码 → 描述、信号方向、历史胜率参考（A 股经验值，非精确值）
VOLUME_PRICE_TABLE = {
    VP_RISE_VOL: {
        "desc": "放量上涨(资金介入)",
        "signal": +1,
        "win_rate": "高",
        "note": "强势确认,胜率历史最高",
    },
    VP_FALL_SHRINK: {
        "desc": "缩量下跌(抛压减轻)",
        "signal": +1,
        "win_rate": "中高",
        "note": "底部蓄势,反弹概率大",
    },
    VP_RISE_SHRINK: {
        "desc": "缩量上涨(量价背离)",
        "signal": -1,
        "win_rate": "低",
        "note": "弱势上涨,警惕回调",
    },
    VP_FALL_VOL: {
        "desc": "放量下跌(主力出货)",
        "signal": -1,
        "win_rate": "极低",
        "note": "危险信号,坚决回避",
    },
    VP_NEUTRAL: {
        "desc": "量价中性",
        "signal": 0,
        "win_rate": "中",
        "note": "无明确方向,等待信号",
    },
}


def get_volume_price_info(state: int) -> dict:
    """查表获取量价状态描述/信号/胜率（P2-26:统一查询入口）。

    Args:
        state: VP_* 枚举值（来自 volume_analysis 返回的 state 字段）

    Returns:
        dict 含 desc/signal/win_rate/note 四个字段；未知状态返回 NEUTRAL。
    """
    return VOLUME_PRICE_TABLE.get(state, VOLUME_PRICE_TABLE[VP_NEUTRAL])


def volume_analysis(closes, volumes, shrink_window: int = 5, shrink_min_days: int = 3):
    """量价分析：量比、天量/地量、量价配合、OBV。

    Args:
        closes: 收盘价序列
        volumes: 成交量序列
        shrink_window: P2-11: 连续缩量检测的最大回溯窗口（默认 5）
        shrink_min_days: P2-11: 触发 shrink_signal 的最小连续天数（默认 3）

    Returns:
        dict 含 volume_ratio/volume_ratio_desc/volume_price/volume_price_signal/
             volume_price_state/obv_divergence/shrink_signal/shrink_desc。
        其中 volume_price_state 为 P2-26 新增枚举（VP_*），
        volume_price_signal 保留 ±1/0 三态方向值。
    """
    if len(closes) < 6 or len(volumes) < 6:
        return None

    recent_vol_avg = statistics.mean(volumes[-5:]) if len(volumes) >= 5 else volumes[-1]
    base_vol_avg = (
        statistics.mean(volumes[-20:-5]) if len(volumes) >= 20 else recent_vol_avg
    )
    volume_ratio = recent_vol_avg / base_vol_avg if base_vol_avg > 0 else 1

    # 量比定性
    if volume_ratio < 0.3:
        vr_desc = "地量(底部信号)"
    elif volume_ratio < 0.5:
        vr_desc = "极度缩量"
    elif volume_ratio < 0.8:
        vr_desc = "缩量"
    elif volume_ratio < 1.2:
        vr_desc = "正常"
    elif volume_ratio < 2.0:
        vr_desc = "放量"
    elif volume_ratio < 3.0:
        vr_desc = "显著放量"
    else:
        vr_desc = "巨量(警惕短期高点)"

    # 量价配合（非对称窗口：近期 5 日 vs 前 20 日，减少短数据集噪声）
    recent_n = min(5, len(closes))
    prev_n = min(20, len(closes) - recent_n)
    if prev_n < 3:
        prev_n = max(len(closes) - recent_n, 3)
    recent_c = closes[-recent_n:]
    prev_c = (
        closes[-recent_n - prev_n : -recent_n] if len(closes) > recent_n else closes[:1]
    )
    recent_v = volumes[-recent_n:]
    prev_v = (
        volumes[-recent_n - prev_n : -recent_n]
        if len(volumes) > recent_n
        else volumes[:1]
    )

    price_chg = statistics.mean(recent_c) / max(statistics.mean(prev_c), 0.01) - 1
    vol_chg = statistics.mean(recent_v) / max(statistics.mean(prev_v), 1) - 1

    # P2-26: 用枚举替代散落的字符串
    if price_chg > 0.01 and vol_chg > 0:
        vp_state = VP_RISE_VOL
    elif price_chg < -0.01 and vol_chg < 0:
        vp_state = VP_FALL_SHRINK
    elif price_chg > 0.01 and vol_chg < 0:
        vp_state = VP_RISE_SHRINK
    elif price_chg < -0.01 and vol_chg > 0:
        vp_state = VP_FALL_VOL
    else:
        vp_state = VP_NEUTRAL

    vp_info = VOLUME_PRICE_TABLE[vp_state]
    vp_desc = vp_info["desc"]
    vp_signal = vp_info["signal"]

    # OBV 及背离
    obv_values = _obv_series(closes, volumes)
    obv_div = _detect_obv_divergence(closes, obv_values)

    # 连续缩量检测（signals.py 引用 shrink_signal / shrink_desc）
    shrink_signal = 0
    shrink_desc = ""
    if len(volumes) >= shrink_window:
        shrink_days = 0
        # M1 修复：最多回溯 shrink_window 根（shrink_window 次比较）。
        # 原实现 range(n-1, max(0, n-shrink_window-1)-1, -1) 产生
        # shrink_window+1 次比较，可误报"连续6日缩量"（shrink_window=5 时）。
        n = len(volumes)
        for k in range(n - 1, max(0, n - shrink_window) - 1, -1):
            if k - 1 >= 0 and volumes[k] < volumes[k - 1]:
                shrink_days += 1
            else:
                break
        if shrink_days >= shrink_min_days:
            shrink_signal = 1
            shrink_desc = f"连续{shrink_days}日缩量(抛压枯竭，底部信号)"

    return {
        "volume_ratio": round(volume_ratio, 2),
        "volume_ratio_desc": vr_desc,
        "volume_price": vp_desc,
        "volume_price_signal": vp_signal,
        "volume_price_state": vp_state,  # P2-26 新增枚举
        "obv_divergence": obv_div,
        "shrink_signal": shrink_signal,
        "shrink_desc": shrink_desc,
    }


def _obv_series(closes, volumes):
    """OBV 序列。"""
    n = min(len(closes), len(volumes))
    if n == 0:
        return []
    obv = [0]
    for i in range(1, n):
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    return obv


def _detect_obv_divergence(closes, obv_series):
    """OBV 顶/底背离。"""
    if len(closes) < 40 or len(obv_series) < 40:
        return None
    lookback = min(40, len(closes))
    c = closes[-lookback:]
    o = obv_series[-lookback:]

    price_highs, price_lows = _find_swing_points(c, window=5)
    obv_highs, obv_lows = _find_swing_points(o, window=5)

    if len(price_highs) >= 2 and len(obv_highs) >= 2:
        last2_p = sorted(price_highs[-2:])
        if last2_p[1] - last2_p[0] >= 8 and c[last2_p[1]] > c[last2_p[0]]:
            relevant = sorted(
                [
                    i
                    for i in obv_highs
                    if abs(i - last2_p[0]) <= 5 or abs(i - last2_p[1]) <= 5
                ]
            )
            if len(relevant) >= 2 and o[relevant[-1]] < o[relevant[0]]:
                return "OBV顶背离"

    if len(price_lows) >= 2 and len(obv_lows) >= 2:
        last2_p = sorted(price_lows[-2:])
        if last2_p[1] - last2_p[0] >= 8 and c[last2_p[1]] < c[last2_p[0]]:
            relevant = sorted(
                [
                    i
                    for i in obv_lows
                    if abs(i - last2_p[0]) <= 5 or abs(i - last2_p[1]) <= 5
                ]
            )
            if len(relevant) >= 2 and o[relevant[-1]] > o[relevant[0]]:
                return "OBV底背离"
    return None
