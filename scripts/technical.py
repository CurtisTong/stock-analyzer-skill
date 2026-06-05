#!/usr/bin/env python3
"""
A 股纯技术分析脚本。
用法:
  technical.py sh600989                    # 完整技术分析报告
  technical.py sh600989 --quick            # 快速摘要
  technical.py sh600989 --scale 60         # 60分钟K线
  technical.py sh600989 -j                 # JSON 输出
  technical.py sh600989 --quick -j         # JSON 快速摘要
"""
import argparse
import json
import math
import statistics
import sys
from datetime import datetime

from common import (
    board_type,
    clamp,
    normalize_quote_code,
    to_float,
)
from kline import fetch as fetch_kline
from quote import fetch_batch

# ═══════════════════════════════════════════════════════════════
# L2: 数学工具
# ═══════════════════════════════════════════════════════════════

def sma(values, period):
    """简单移动平均。"""
    if len(values) < period:
        return statistics.mean(values) if values else 0
    return statistics.mean(values[-period:])


def ema(values, period):
    """指数移动平均。"""
    if len(values) < period:
        return statistics.mean(values) if values else 0
    k = 2 / (period + 1)
    result = statistics.mean(values[:period])
    for v in values[period:]:
        result = v * k + result * (1 - k)
    return result


def _ema_series(values, period):
    """返回 EMA 序列（用于背离检测和 KDJ）。"""
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    result = [statistics.mean(values[:period])]
    for v in values[period:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def stddev(values):
    """总体标准差。"""
    if len(values) < 2:
        return 0
    mean = statistics.mean(values)
    return math.sqrt(sum((x - mean) ** 2 for x in values) / len(values))


def _find_swing_points(values, window=5):
    """找局部极值点索引列表。用于背离检测。"""
    if len(values) < 2 * window + 1:
        return [], []
    highs, lows = [], []
    for i in range(window, len(values) - window):
        left = values[i - window:i]
        right = values[i + 1:i + window + 1]
        if values[i] >= max(left) and values[i] > max(right):
            highs.append(i)
        if values[i] <= min(left) and values[i] < min(right):
            lows.append(i)
    return highs, lows


# ═══════════════════════════════════════════════════════════════
# L3: 均线系统
# ═══════════════════════════════════════════════════════════════

_MA_PERIODS = [5, 10, 20, 60, 120, 250]

def ma_system(closes):
    """均线系统分析。返回 MA 值、排列状态、粘合度、支撑/阻力均线。"""
    result = {}
    for p in _MA_PERIODS:
        result[f"ma{p}"] = round(sma(closes, p), 2) if len(closes) >= p else None

    # 排列状态
    mas = [result[f"ma{p}"] for p in _MA_PERIODS if result[f"ma{p}"] is not None]
    if len(mas) >= 4:
        if all(mas[i] > mas[i+1] for i in range(len(mas)-1) if mas[i] and mas[i+1]):
            result["alignment"] = "多头排列"
        elif all(mas[i] < mas[i+1] for i in range(len(mas)-1) if mas[i] and mas[i+1]):
            result["alignment"] = "空头排列"
        else:
            result["alignment"] = "交叉震荡"
    else:
        result["alignment"] = "数据不足"

    # MA 粘合度 (MA5/10/20)
    short_mas = [result.get(f"ma{p}") for p in [5, 10, 20] if result.get(f"ma{p}")]
    if len(short_mas) >= 3 and statistics.mean(short_mas) > 0:
        conv = stddev(short_mas) / statistics.mean(short_mas)
        result["convergence"] = round(conv, 4)
        if conv < 0.02:
            result["convergence_desc"] = "高度粘合(变盘窗口)"
        elif conv < 0.05:
            result["convergence_desc"] = "中度粘合"
        else:
            result["convergence_desc"] = "发散"
    else:
        result["convergence"] = None
        result["convergence_desc"] = "数据不足"

    # 支撑/阻力均线（相对当前价格）
    last = closes[-1] if closes else 0
    supports, resistances = [], []
    for p in _MA_PERIODS:
        v = result.get(f"ma{p}")
        if v is None:
            continue
        if v < last:
            supports.append((f"MA{p}", v))
        else:
            resistances.append((f"MA{p}", v))
    result["ma_supports"] = sorted(supports, key=lambda x: x[1], reverse=True)
    result["ma_resistances"] = sorted(resistances, key=lambda x: x[1])
    return result


# ═══════════════════════════════════════════════════════════════
# L4: MACD 增强（含背离检测）
# ═══════════════════════════════════════════════════════════════

def macd_full(closes):
    """MACD 完整分析：DIF/DEA/柱/金叉死叉 + 顶背离/底背离。"""
    if len(closes) < 34:
        return None

    # DIF/DEA
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    dif = ema12 - ema26

    # 计算 DIF 序列
    ema12_series = _ema_series(closes, 12)
    ema26_series = _ema_series(closes, 26)
    min_len = min(len(ema12_series), len(ema26_series))
    dif_series = [ema12_series[i] - ema26_series[i] for i in range(min_len)]

    dea_series = _ema_series(dif_series, 9)
    dea = dea_series[-1] if dea_series else dif
    prev_dif = dif_series[-2] if len(dif_series) >= 2 else dif
    prev_dea = dea_series[-2] if len(dea_series) >= 2 else dea
    macd_bar = (dif - dea) * 2

    # 金叉死叉检测
    signal = 0
    if prev_dif <= prev_dea and dif > dea:
        signal = 1
    elif prev_dif >= prev_dea and dif < dea:
        signal = -1

    # 柱状图趋势
    prev_bar = (prev_dif - prev_dea) * 2
    if macd_bar > 0 and macd_bar > prev_bar:
        bar_trend = "红柱放大"
    elif macd_bar > 0 and macd_bar <= prev_bar:
        bar_trend = "红柱缩小"
    elif macd_bar < 0 and macd_bar < prev_bar:
        bar_trend = "绿柱放大"
    else:
        bar_trend = "绿柱缩小"

    # 背离检测
    divergence = _detect_macd_divergence(closes, dif_series, dea_series)

    return {
        "dif": round(dif, 4),
        "dea": round(dea, 4),
        "macd_bar": round(macd_bar, 4),
        "signal": signal,
        "signal_desc": {1: "金叉", -1: "死叉", 0: "无"}.get(signal),
        "bar_trend": bar_trend,
        "divergence": divergence,
    }


def _detect_macd_divergence(closes, dif_series, dea_series):
    """检测 MACD 顶背离/底背离。"""
    if len(closes) < 60 or len(dif_series) < 60:
        return None

    lookback = min(60, len(closes))
    c = closes[-lookback:]
    d = dif_series[-lookback:]

    price_highs, price_lows = _find_swing_points(c, window=5)
    dif_highs, dif_lows = _find_swing_points(d, window=5)

    # 顶背离：价格新高而 DIF 未新高
    if len(price_highs) >= 2:
        last2_p = sorted(price_highs[-2:])
        if last2_p[1] - last2_p[0] >= 8:
            if c[last2_p[1]] > c[last2_p[0]]:
                # 找到对应的 DIF 峰值
                relevant_dif_peaks = [i for i in dif_highs if abs(i - last2_p[0]) <= 5 or abs(i - last2_p[1]) <= 5]
                if len(relevant_dif_peaks) >= 2:
                    relevant_dif_peaks.sort()
                    if d[relevant_dif_peaks[-1]] < d[relevant_dif_peaks[0]]:
                        return "顶背离(看跌)"

    # 底背离：价格新低而 DIF 未新低
    if len(price_lows) >= 2:
        last2_p = sorted(price_lows[-2:])
        if last2_p[1] - last2_p[0] >= 8:
            if c[last2_p[1]] < c[last2_p[0]]:
                relevant_dif_lows = [i for i in dif_lows if abs(i - last2_p[0]) <= 5 or abs(i - last2_p[1]) <= 5]
                if len(relevant_dif_lows) >= 2:
                    relevant_dif_lows.sort()
                    if d[relevant_dif_lows[-1]] > d[relevant_dif_lows[0]]:
                        return "底背离(看涨)"

    return None


# ═══════════════════════════════════════════════════════════════
# L5: KDJ
# ═══════════════════════════════════════════════════════════════

def kdj_full(closes, highs, lows, n=9):
    """KDJ 指标 + 钝化检测。"""
    if len(closes) < n + 1:
        return None

    # 计算 KDJ 序列
    k_series, d_series = [], []
    k_val, d_val = 50, 50
    for i in range(n - 1, len(closes)):
        low_n = min(lows[i - n + 1:i + 1])
        high_n = max(highs[i - n + 1:i + 1])
        rsv = ((closes[i] - low_n) / (high_n - low_n) * 100) if high_n != low_n else 50
        k_val = 2 / 3 * k_val + 1 / 3 * rsv
        d_val = 2 / 3 * d_val + 1 / 3 * k_val
        k_series.append(k_val)
        d_series.append(d_val)

    k_now = k_series[-1]
    d_now = d_series[-1]
    j_now = 3 * k_now - 2 * d_now

    # 金叉死叉
    kdj_signal = "正常"
    if len(k_series) >= 2:
        if k_series[-2] <= d_series[-2] and k_now > d_now:
            kdj_signal = "金叉"
        elif k_series[-2] >= d_series[-2] and k_now < d_now:
            kdj_signal = "死叉"

    # 超买超卖区
    if j_now > 100:
        kdj_signal = f"超买区(J={j_now:.0f})"
    elif j_now < 0:
        kdj_signal = f"超卖区(J={j_now:.0f})"

    # A 股特化：KDJ 钝化检测
    dunhua = False
    if len(k_series) >= 5:
        if all(k > 80 for k in k_series[-5:]):
            dunhua = True
            kdj_signal += " [KDJ高位钝化-趋势延续]"
        elif all(k < 20 for k in k_series[-5:]):
            dunhua = True
            kdj_signal += " [KDJ低位钝化-趋势延续]"

    return {
        "k": round(k_now, 2),
        "d": round(d_now, 2),
        "j": round(j_now, 2),
        "signal": kdj_signal,
        "钝化": dunhua,
    }


# ═══════════════════════════════════════════════════════════════
# L6: BOLL 布林带
# ═══════════════════════════════════════════════════════════════

def bollinger(closes, period=20, multiplier=2.0):
    """布林带分析：上/中/下轨 + 带宽 + 价格位置。"""
    if len(closes) < period:
        return None

    mid = sma(closes, period)
    sd = stddev(closes[-period:])
    upper = mid + multiplier * sd
    lower = mid - multiplier * sd
    bandwidth = (upper - lower) / mid if mid > 0 else 0
    last = closes[-1]
    position = (last - lower) / (upper - lower) if upper != lower else 0.5

    # 带宽状态
    if bandwidth < 0.05:
        bw_desc = "极度收窄(变盘信号)"
    elif bandwidth < 0.10:
        bw_desc = "收窄中"
    else:
        bw_desc = "正常带宽"

    # 价格位置
    if position > 0.9:
        pos_desc = "触及上轨"
    elif position < 0.1:
        pos_desc = "触及下轨"
    elif position > 0.7:
        pos_desc = "偏上轨"
    elif position < 0.3:
        pos_desc = "偏下轨"
    else:
        pos_desc = "中轨附近"

    return {
        "upper": round(upper, 2),
        "mid": round(mid, 2),
        "lower": round(lower, 2),
        "bandwidth": round(bandwidth, 4),
        "bandwidth_desc": bw_desc,
        "position": round(position, 3),
        "position_desc": pos_desc,
    }


# ═══════════════════════════════════════════════════════════════
# L7: 成交量分析
# ═══════════════════════════════════════════════════════════════

def volume_analysis(closes, volumes):
    """量价分析：量比、天量/地量、量价配合、OBV。"""
    if len(closes) < 6 or len(volumes) < 6:
        return None

    last = closes[-1]
    recent_vol_avg = statistics.mean(volumes[-5:]) if len(volumes) >= 5 else volumes[-1]
    base_vol_avg = statistics.mean(volumes[-20:-5]) if len(volumes) >= 20 else recent_vol_avg
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

    # 量价配合
    mid = max(len(closes) // 2, 3)
    recent_c = closes[-mid:]
    prev_c = closes[:mid]
    recent_v = volumes[-mid:]
    prev_v = volumes[:mid]

    price_chg = statistics.mean(recent_c) / max(statistics.mean(prev_c), 0.01) - 1
    vol_chg = statistics.mean(recent_v) / max(statistics.mean(prev_v), 0.01) - 1

    if price_chg > 0.01 and vol_chg > 0:
        vp_desc = "放量上涨(资金介入)"
        vp_signal = 1
    elif price_chg < -0.01 and vol_chg < 0:
        vp_desc = "缩量下跌(抛压减轻)"
        vp_signal = 1
    elif price_chg > 0.01 and vol_chg < 0:
        vp_desc = "缩量上涨(量价背离)"
        vp_signal = -1
    elif price_chg < -0.01 and vol_chg > 0:
        vp_desc = "放量下跌(主力出货)"
        vp_signal = -1
    else:
        vp_desc = "量价中性"
        vp_signal = 0

    # OBV 及背离
    obv_values = _obv_series(closes, volumes)
    obv_now = obv_values[-1] if obv_values else 0
    obv_div = _detect_obv_divergence(closes, obv_values)

    return {
        "volume_ratio": round(volume_ratio, 2),
        "volume_ratio_desc": vr_desc,
        "volume_price": vp_desc,
        "volume_price_signal": vp_signal,
        "obv_divergence": obv_div,
    }


def _obv_series(closes, volumes):
    """OBV 序列。"""
    obv = [0]
    for i in range(1, len(closes)):
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
            relevant = sorted([i for i in obv_highs if abs(i - last2_p[0]) <= 5 or abs(i - last2_p[1]) <= 5])
            if len(relevant) >= 2 and o[relevant[-1]] < o[relevant[0]]:
                return "OBV顶背离"

    if len(price_lows) >= 2 and len(obv_lows) >= 2:
        last2_p = sorted(price_lows[-2:])
        if last2_p[1] - last2_p[0] >= 8 and c[last2_p[1]] < c[last2_p[0]]:
            relevant = sorted([i for i in obv_lows if abs(i - last2_p[0]) <= 5 or abs(i - last2_p[1]) <= 5])
            if len(relevant) >= 2 and o[relevant[-1]] > o[relevant[0]]:
                return "OBV底背离"
    return None


# ═══════════════════════════════════════════════════════════════
# L8: K线形态识别
# ═══════════════════════════════════════════════════════════════

def detect_candle_patterns(records):
    """识别最近 4 根 K 线的形态。"""
    if len(records) < 4:
        return []

    patterns = []
    bars = []
    for r in records[-4:]:
        bars.append({
            "open": to_float(r.get("open")),
            "high": to_float(r.get("high")),
            "low": to_float(r.get("low")),
            "close": to_float(r.get("close")),
            "date": r.get("day", ""),
        })

    # 单根形态（最近3根）
    for i, b in enumerate(bars[-3:]):
        idx = len(bars) - 3 + i
        prev_close = bars[idx - 1]["close"] if idx > 0 else b["open"]
        singles = _candle_single(b, prev_close)
        for s in singles:
            patterns.append({"date": b["date"], "type": s, "position": f"T-{len(bars)-1-idx}"})

    # A 股特化形态
    if len(bars) >= 2:
        ah = _candle_ashare(bars[-2], bars[-1])
        if ah:
            patterns.append({"date": bars[-1]["date"], "type": ah, "position": "T-0"})

    # 双根组合
    if len(bars) >= 2:
        doubles = _candle_double(bars[-2], bars[-1])
        for d in doubles:
            patterns.append({"date": bars[-1]["date"], "type": d, "position": "T-1~0"})

    # 三根组合
    if len(bars) >= 3:
        triples = _candle_triple(bars[-3], bars[-2], bars[-1])
        for t in triples:
            patterns.append({"date": bars[-1]["date"], "type": t, "position": "T-2~0"})

    return patterns


def _body_shadow(bar):
    """计算实体、上影线、下影线。"""
    body = abs(bar["close"] - bar["open"])
    upper_shadow = bar["high"] - max(bar["close"], bar["open"])
    lower_shadow = min(bar["close"], bar["open"]) - bar["low"]
    total = bar["high"] - bar["low"]
    return body, upper_shadow, lower_shadow, total


def _is_bullish(bar):
    return bar["close"] > bar["open"]


def _candle_single(bar, prev_close):
    """单根 K 线形态识别。"""
    body, upper, lower, total = _body_shadow(bar)
    if total <= 0:
        return []
    patterns = []

    # 十字星
    if body / total < 0.1:
        patterns.append("十字星(变盘信号)")
    # 锤子线
    elif lower > 2 * body and (bar["high"] - bar["close"]) < body:
        patterns.append("锤子线(底部反转)")
    # 倒锤子
    elif upper > 2 * body and (bar["close"] - bar["low"]) < body:
        patterns.append("倒锤子(可能见顶)")
    # 光头光脚阳线
    elif _is_bullish(bar) and bar["close"] == bar["high"] and bar["open"] == bar["low"]:
        patterns.append("光头光脚阳线(强势)")
    # 光头光脚阴线
    elif not _is_bullish(bar) and bar["open"] == bar["high"] and bar["close"] == bar["low"]:
        patterns.append("光头光脚阴线(弱势)")
    # T 字线
    elif body / total < 0.05 and upper < body and lower > 3 * body:
        patterns.append("T字线(下方支撑强)")
    # 倒 T 字
    elif body / total < 0.05 and lower < body and upper > 3 * body:
        patterns.append("倒T字(上方压力大)")

    return patterns


def _candle_ashare(prev, curr):
    """A 股特化形态。"""
    if _is_bullish(curr):
        if curr["close"] < prev["close"]:
            return "假阳真阴(收阳但实际下跌)"
    else:
        if curr["close"] > prev["close"]:
            return "假阴真阳(收阴但实际上涨)"
    return None


def _candle_double(b1, b2):
    """双根 K 线组合。"""
    patterns = []
    # 阳包阴
    if not _is_bullish(b1) and _is_bullish(b2) and b2["close"] > b1["open"] and b2["open"] < b1["close"]:
        patterns.append("阳包阴(看涨吞没)")
    # 阴包阳
    if _is_bullish(b1) and not _is_bullish(b2) and b2["close"] < b1["open"] and b2["open"] > b1["close"]:
        patterns.append("阴包阳(看跌吞没)")
    # 平底/平顶
    if abs(b1["low"] - b2["low"]) / max(b1["low"], 0.01) < 0.005:
        patterns.append("平底(支撑确认)")
    if abs(b1["high"] - b2["high"]) / max(b1["high"], 0.01) < 0.005:
        patterns.append("平顶(压力确认)")
    # 揉搓线：一长上影一长下影
    body1, upper1, lower1, _ = _body_shadow(b1)
    body2, upper2, lower2, _ = _body_shadow(b2)
    if (upper1 > 2 * body1 and lower2 > 2 * body2) or (lower1 > 2 * body1 and upper2 > 2 * body2):
        patterns.append("揉搓线(洗盘或变盘)")
    return patterns


def _candle_triple(b1, b2, b3):
    """三根 K 线组合。"""
    patterns = []
    body1, _, _, _ = _body_shadow(b1)
    body2, _, _, _ = _body_shadow(b2)
    body3, _, _, _ = _body_shadow(b3)

    # 早晨之星：阴线 + 小实体 + 阳线
    if not _is_bullish(b1) and body2 < body1 * 0.5 and _is_bullish(b3) and b3["close"] > (b1["open"] + b1["close"]) / 2:
        patterns.append("早晨之星(底部反转)")
    # 黄昏之星：阳线 + 小实体 + 阴线
    if _is_bullish(b1) and body2 < body1 * 0.5 and not _is_bullish(b3) and b3["close"] < (b1["open"] + b1["close"]) / 2:
        patterns.append("黄昏之星(顶部反转)")
    # 红三兵
    if _is_bullish(b1) and _is_bullish(b2) and _is_bullish(b3) and b1["close"] < b2["close"] < b3["close"]:
        if b2["open"] > b1["open"] and b3["open"] > b2["open"]:
            patterns.append("红三兵(强势延续)")
    # 三只乌鸦
    if not _is_bullish(b1) and not _is_bullish(b2) and not _is_bullish(b3) and b1["close"] > b2["close"] > b3["close"]:
        patterns.append("三只乌鸦(弱势延续)")
    return patterns


# ═══════════════════════════════════════════════════════════════
# L9: 趋势与结构分析
# ═══════════════════════════════════════════════════════════════

def support_resistance(closes, highs, lows, ma_info):
    """关键支撑/阻力位。"""
    if len(highs) < 10 or len(lows) < 10:
        return {"supports": [], "resistances": []}

    last = closes[-1]

    # 前高前低
    lookback = min(60, len(highs))
    recent_highs = highs[-lookback:]
    recent_lows = lows[-lookback:]

    # 找局部摇摆点
    ph, pl = _find_swing_points(recent_highs, window=3)
    swing_highs = sorted(set(round(recent_highs[i], 2) for i in ph if recent_highs[i] > last))
    swing_lows = sorted(set(round(recent_lows[i], 2) for i in pl if recent_lows[i] < last), reverse=True)

    supports = []
    resistances = []

    # 均线支撑/阻力
    for name, price in ma_info.get("ma_supports", [])[:3]:
        supports.append({"level": price, "source": name, "strength": "中"})
    for name, price in ma_info.get("ma_resistances", [])[:3]:
        resistances.append({"level": price, "source": name, "strength": "中"})

    # 前低支撑
    for lv in swing_lows[:2]:
        supports.append({"level": lv, "source": "前低", "strength": "强"})

    # 前高阻力
    for hv in swing_highs[-2:]:
        resistances.append({"level": hv, "source": "前高", "strength": "强"})

    # 整数关口
    round_num = round(last, -1 if last >= 10 else 0)
    if round_num < last:
        base = round_num
        for i in range(1, 4):
            r = base - i * (10 if last >= 50 else 1)
            if r > 0:
                supports.append({"level": r, "source": "整数关口", "strength": "弱"})
    else:
        base = round_num + (10 if last >= 50 else 1)
        for i in range(3):
            resistances.append({"level": base + i * (10 if last >= 50 else 1), "source": "整数关口", "strength": "弱"})

    # 去重排序
    supports = sorted(supports, key=lambda x: x["level"], reverse=True)[:5]
    resistances = sorted(resistances, key=lambda x: x["level"])[:5]

    nearest_support = supports[0]["level"] if supports else None
    nearest_resistance = resistances[0]["level"] if resistances else None

    return {
        "supports": supports[:3],
        "resistances": resistances[:3],
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
    }


def box_detection(highs, lows, closes, window=20):
    """箱体震荡检测。"""
    if len(closes) < window:
        return None
    hh = max(highs[-window:])
    ll = min(lows[-window:])
    avg = statistics.mean(closes[-window:])
    range_pct = (hh - ll) / avg if avg > 0 else 0

    if range_pct < 0.03:
        return None

    mid = (hh + ll) / 2
    in_box = sum(1 for c in closes[-window:] if ll + (hh - ll) * 0.1 < c < hh - (hh - ll) * 0.1)
    if in_box / window >= 0.6:
        return {
            "top": round(hh, 2),
            "bottom": round(ll, 2),
            "mid": round(mid, 2),
            "range_pct": round(range_pct * 100, 1),
            "days": window,
            "status": "箱体震荡",
            "position": round((closes[-1] - ll) / (hh - ll) * 100) if hh != ll else 50,
        }
    return None


def breakout_check(closes, highs, volumes, resistance):
    """突破检测。"""
    if len(closes) < 21:
        return {"status": "数据不足"}
    last = closes[-1]
    prev = closes[-2]
    avg_vol20 = statistics.mean(volumes[-21:-1]) if len(volumes) >= 21 else statistics.mean(volumes[:-1])
    last_vol = volumes[-1]

    broke = last > resistance and prev <= resistance
    if not broke:
        # 之前突破现在回踩
        recent_above = all(c > resistance for c in closes[-5:])
        if recent_above and last < resistance * 1.01:
            return {"status": "回踩确认中", "resistance": round(resistance, 2)}
        return {"status": "未突破"}

    vol_confirm = last_vol > 1.5 * avg_vol20
    return {
        "status": "突破确认(放量)" if vol_confirm else "突破待确认(缩量)",
        "resistance": round(resistance, 2),
        "volume_ratio": round(last_vol / avg_vol20, 2) if avg_vol20 > 0 else 0,
    }


def wave_state(closes, highs, lows):
    """简易波浪状态。"""
    if len(closes) < 40:
        return "数据不足"
    lookback = min(60, len(closes))
    c = closes[-lookback:]
    ph, pl = _find_swing_points(c, window=5)

    if len(ph) >= 2 and len(pl) >= 2:
        recent_ph = sorted(ph[-3:]) if len(ph) >= 3 else sorted(ph)
        recent_pl = sorted(pl[-3:]) if len(pl) >= 3 else sorted(pl)
        if recent_ph[-1] > recent_ph[0] and recent_pl[-1] > recent_pl[0]:
            return "上升浪(高点抬高+低点抬高)"
        elif recent_ph[-1] < recent_ph[0] and recent_pl[-1] < recent_pl[0]:
            return "下跌浪(高点降低+低点降低)"
        elif recent_ph[-1] > recent_ph[0]:
            return "可能有顶部结构(高点抬高但MACD需确认)"
        elif recent_pl[-1] > recent_pl[0]:
            return "可能有底部结构(低点抬高)"
    return "盘整"


# ═══════════════════════════════════════════════════════════════
# L10: A 股特化分析
# ═══════════════════════════════════════════════════════════════

_LIMIT_RATIOS = {"主板": 9.5, "创业板": 19.5, "科创板": 19.5, "北交所": 29.5}

def limit_analysis(records, board, quote):
    """涨跌停/连板分析。"""
    if len(records) < 10:
        return None

    limit_ratio = _LIMIT_RATIOS.get(board, 9.5)
    limit_up_price = to_float(quote.get("limit_up"))
    limit_down_price = to_float(quote.get("limit_down"))
    last_close = to_float(records[-1].get("close"))
    last_high = to_float(records[-1].get("high"))
    last_low = to_float(records[-1].get("low"))
    last_open = to_float(records[-1].get("open"))

    result = {
        "board": board,
        "limit_ratio": limit_ratio,
        "limit_up_price": limit_up_price,
        "limit_down_price": limit_down_price,
    }

    # 当前涨跌停状态
    if limit_up_price > 0 and last_close >= limit_up_price * 0.995:
        result["board_status"] = "封涨停"
    elif last_low <= limit_down_price * 1.005 if limit_down_price > 0 else False:
        if last_close > limit_down_price * 1.01:
            result["board_status"] = "翘板(跌停打开)"
        else:
            result["board_status"] = "封跌停"
    elif last_high >= limit_up_price * 0.995 and last_close < limit_up_price * 0.995:
        gap = (limit_up_price - last_close) / limit_up_price * 100
        result["board_status"] = f"炸板(离涨停差{gap:.1f}%)"
    else:
        result["board_status"] = "正常交易"

    # 连板检测
    streak = _count_limit_streak(records, limit_ratio)
    result["limit_streak"] = streak

    if streak > 0:
        if streak == 1:
            result["streak_type"] = "首板"
        elif streak == 2:
            result["streak_type"] = "二板(连板确认)"
        elif streak <= 4:
            result["streak_type"] = f"高位{streak}板"
        else:
            result["streak_type"] = f"妖股({streak}连板)"

        # 连板量能分析
        recent_bars = records[-streak:]
        vols = [to_float(r.get("volume")) for r in recent_bars]
        if len(vols) >= 2 and vols[0] > 0:
            if all(vols[i] < vols[i-1] for i in range(1, len(vols))):
                result["streak_volume"] = "缩量加速(强-惜售)"
            elif vols[-1] > vols[0] * 1.5:
                result["streak_volume"] = "放量分歧(弱-换手加大)"
            else:
                result["streak_volume"] = "量能稳定(中性)"
    else:
        result["streak_type"] = "无连板"

    # T+1 风险提示
    if streak >= 1 and result.get("board_status") == "封涨停":
        result["t1_risk"] = "T+1隔夜风险：今日追板仓位明日方可卖出，需关注次日溢价和核按钮风险"
    else:
        result["t1_risk"] = None

    return result


def _count_limit_streak(records, limit_ratio):
    """计算当前连板数。"""
    count = 0
    for i in range(len(records) - 1, -1, -1):
        r = records[i]
        close = to_float(r.get("close"))
        prev_close = to_float(records[i - 1].get("close")) if i > 0 else close
        if prev_close <= 0:
            continue
        chg_pct = (close / prev_close - 1) * 100
        if i == len(records) - 1:
            if chg_pct >= limit_ratio * 0.95:
                count = 1
        elif count > 0 and chg_pct >= limit_ratio * 0.95:
            count += 1
        else:
            break
    return count


# ═══════════════════════════════════════════════════════════════
# L11: 综合评分
# ═══════════════════════════════════════════════════════════════

def rsi_features(closes, period=14):
    """RSI 计算（从 screener 移植）。"""
    if len(closes) < period + 1:
        return {"rsi": 50, "signal": 0}
    gains, losses = [], []
    for i in range(-period, 0):
        chg = closes[i] - closes[i - 1]
        if chg >= 0:
            gains.append(chg)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(-chg)
    avg_gain = statistics.mean(gains)
    avg_loss = statistics.mean(losses)
    if avg_loss == 0:
        rsi = 100
    else:
        rsi = 100 - 100 / (1 + avg_gain / avg_loss)
    signal = 0
    if rsi < 30:
        signal = 1
    elif rsi > 70:
        signal = -1
    return {"rsi": round(rsi, 1), "signal": signal}


def composite_score(features):
    """多指标共振评分 0-100。"""
    score = 0
    ma = features.get("ma_system", {})
    macd = features.get("macd") or {}
    kdj = features.get("kdj") or {}
    boll = features.get("bollinger") or {}
    rsi_data = features.get("rsi", {})
    vol = features.get("volume") or {}
    patterns = features.get("patterns", [])

    # 1. 均线 20 分
    alignment = ma.get("alignment", "")
    if alignment == "多头排列":
        score += 20
    elif alignment == "交叉震荡":
        score += 12
    elif alignment == "空头排列":
        score += 3
    else:
        score += 7

    # 2. MACD 15 分
    macd_signal = macd.get("signal", 0)
    bar_trend = macd.get("bar_trend", "")
    divergence = macd.get("divergence", "")
    if macd_signal == 1 and "放大" in bar_trend:
        score += 15
    elif macd_signal == 1:
        score += 10
    elif macd_signal == 0:
        score += 7
    elif macd_signal == -1:
        score += 3
    if divergence == "底背离(看涨)":
        score += 8
    elif divergence == "顶背离(看跌)":
        score -= 8

    # 3. KDJ 15 分
    kdj_weight = 5 if kdj.get("钝化") else 15
    kdj_sig = kdj.get("signal", "")
    if "金叉" in kdj_sig and "超卖" in kdj_sig:
        score += kdj_weight
    elif "金叉" in kdj_sig:
        score += kdj_weight * 0.8
    elif "超卖" in kdj_sig:
        score += kdj_weight * 0.6
    elif "死叉" in kdj_sig:
        score += kdj_weight * 0.2
    else:
        score += kdj_weight * 0.45

    # 4. BOLL 10 分
    pos = boll.get("position", 0.5)
    bw = boll.get("bandwidth_desc", "")
    if pos < 0.3 and "收窄" in bw:
        score += 10
    elif 0.3 <= pos <= 0.7:
        score += 7
    elif pos > 0.7:
        score += 4
    else:
        score += 5

    # 5. RSI 10 分
    rsi = rsi_data.get("rsi", 50)
    if 30 <= rsi <= 40:
        score += 10
    elif 40 < rsi <= 60:
        score += 7
    elif 20 <= rsi < 30:
        score += 8
    elif 60 < rsi <= 70:
        score += 5
    elif rsi > 70:
        score += 3
    else:
        score += 5

    # 6. 成交量 15 分
    vp_signal = vol.get("volume_price_signal", 0)
    vr = vol.get("volume_ratio", 1)
    if vp_signal == 1:
        score += 12
    elif vp_signal == 0:
        score += 7
    else:
        score += 3
    if vr < 0.3:
        score += 3

    # 7. K线形态 15 分
    bullish_patterns = ["早晨之星", "阳包阴", "锤子线", "红三兵", "假阴真阳"]
    bearish_patterns = ["黄昏之星", "阴包阳", "倒锤子", "三只乌鸦", "假阳真阴"]
    pattern_score = 7  # neutral base
    for p in patterns:
        ptype = p.get("type", "")
        if any(b in ptype for b in bullish_patterns):
            pattern_score = max(pattern_score, 13)
        if any(b in ptype for b in bearish_patterns):
            pattern_score = min(pattern_score, 3)
    score += pattern_score

    score = clamp(score, 0, 100)

    # 定级
    if score >= 80:
        grade = "强烈看多"
    elif score >= 60:
        grade = "偏多"
    elif score >= 40:
        grade = "中性"
    elif score >= 20:
        grade = "偏空"
    else:
        grade = "强烈看空"

    # 生成买卖信号
    buy_signals, sell_signals = _generate_signals(features)

    return {
        "score": round(score, 1),
        "grade": grade,
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
    }


def _generate_signals(features):
    """汇总买卖信号。"""
    buy, sell = [], []
    ma = features.get("ma_system", {})
    macd = features.get("macd") or {}
    kdj = features.get("kdj") or {}
    boll = features.get("bollinger") or {}
    rsi_data = features.get("rsi", {})
    vol = features.get("volume") or {}
    vol_price = vol.get("volume_price", "")
    vol_vp = vol.get("volume_price_signal", 0)
    divergence = macd.get("divergence", "")

    # 买入信号
    if macd.get("signal") == 1:
        buy.append("MACD金叉")
    if divergence == "底背离(看涨)":
        buy.append("MACD底背离")
    if "金叉" in kdj.get("signal", "") and "超卖" in kdj.get("signal", ""):
        buy.append("KDJ超卖区金叉")
    if boll.get("position", 0.5) < 0.2 and "收窄" in boll.get("bandwidth_desc", ""):
        buy.append("BOLL下轨+收窄(变盘)")
    if rsi_data.get("rsi", 50) < 35:
        buy.append(f"RSI超卖({rsi_data.get('rsi')})")
    if vol_vp == 1 and "放量上涨" in vol_price:
        buy.append("放量上涨(资金介入)")

    # 卖出信号
    if macd.get("signal") == -1:
        sell.append("MACD死叉")
    if divergence == "顶背离(看跌)":
        sell.append("MACD顶背离")
    if "死叉" in kdj.get("signal", "") or "超买" in kdj.get("signal", ""):
        sell.append(f"KDJ{kdj.get('signal')}")
    if boll.get("position", 0.5) > 0.8:
        sell.append("BOLL触及上轨")
    if rsi_data.get("rsi", 50) > 70:
        sell.append(f"RSI超买({rsi_data.get('rsi')})")
    if vol_vp == -1 and "出货" in vol_price:
        sell.append("放量下跌(主力出货)")

    return buy, sell


# ═══════════════════════════════════════════════════════════════
# L13: 渲染输出
# ═══════════════════════════════════════════════════════════════

def _fmt(val, default="-"):
    return str(val) if val is not None else default


def render_report(features, score, signals, meta):
    """完整技术分析报告。"""
    lines = []
    ma = features.get("ma_system", {})
    macd = features.get("macd") or {}
    kdj = features.get("kdj") or {}
    boll = features.get("bollinger") or {}
    rsi_data = features.get("rsi", {})
    vol = features.get("volume") or {}
    sr = features.get("support_resistance", {})
    box = features.get("box")
    breakout = features.get("breakout", {})
    wave = features.get("wave", "")
    patterns = features.get("patterns", [])
    limit_data = features.get("limit_analysis") or {}

    lines.append("═" * 72)
    lines.append(f"  {meta['name']} ({meta['code']})  现价: {meta['price']}  涨跌: {meta['change_pct']}%  板块: {meta['board']}  时间: {meta['timestamp']}")
    lines.append("═" * 72)

    # ── 综合评分 ──
    lines.append(f"\n## 综合评分: {score['score']}/100 -- {score['grade']}")
    if score["buy_signals"]:
        lines.append(f"  买入信号: {', '.join(score['buy_signals'])}")
    if score["sell_signals"]:
        lines.append(f"  卖出信号: {', '.join(score['sell_signals'])}")
    if sr.get("nearest_support"):
        lines.append(f"  关键支撑: {sr['nearest_support']}  关键阻力: {sr.get('nearest_resistance', '-')}")

    # ── 均线系统 ──
    lines.append(f"\n## 均线系统")
    ma_parts = []
    for p in [5, 10, 20, 60, 120, 250]:
        v = ma.get(f"ma{p}")
        if v is not None:
            ma_parts.append(f"MA{p}: {v}")
    lines.append(f"  {', '.join(ma_parts)}")
    lines.append(f"  排列: {ma.get('alignment', '-')}  |  粘合度: {ma.get('convergence_desc', '-')}")

    # ── MACD ──
    lines.append(f"\n## MACD")
    lines.append(f"  DIF: {_fmt(macd.get('dif'))}  DEA: {_fmt(macd.get('dea'))}  BAR: {_fmt(macd.get('macd_bar'))}")
    lines.append(f"  信号: {macd.get('signal_desc', '-')}  |  柱趋势: {macd.get('bar_trend', '-')}")
    if macd.get("divergence"):
        lines.append(f"  背离: **{macd['divergence']}**")

    # ── KDJ ──
    lines.append(f"\n## KDJ")
    lines.append(f"  K: {_fmt(kdj.get('k'))}  D: {_fmt(kdj.get('d'))}  J: {_fmt(kdj.get('j'))}")
    lines.append(f"  信号: {kdj.get('signal', '-')}")
    if kdj.get("钝化"):
        lines.append(f"  ⚠ KDJ钝化中，超买超卖信号暂停参考")

    # ── BOLL ──
    lines.append(f"\n## BOLL")
    lines.append(f"  上轨: {_fmt(boll.get('upper'))}  中轨: {_fmt(boll.get('mid'))}  下轨: {_fmt(boll.get('lower'))}")
    lines.append(f"  带宽: {boll.get('bandwidth_desc', '-')}  |  价格: {boll.get('position_desc', '-')}")

    # ── 成交量 ──
    lines.append(f"\n## 成交量")
    lines.append(f"  量比: {_fmt(vol.get('volume_ratio'))} ({vol.get('volume_ratio_desc', '-')})")
    lines.append(f"  量价: {vol.get('volume_price', '-')}")
    if vol.get("obv_divergence"):
        lines.append(f"  OBV: {vol['obv_divergence']}")

    # ── RSI ──
    lines.append(f"\n## RSI")
    rsi_desc = {1: "超卖", -1: "超买"}.get(rsi_data.get("signal", 0), "正常")
    lines.append(f"  RSI-{rsi_data.get('period', 14)}: {rsi_data.get('rsi', 50)} ({rsi_desc})")

    # ── K线形态 ──
    if patterns:
        lines.append(f"\n## K线形态")
        for p in patterns:
            lines.append(f"  {p['position']} [{p['date']}] {p['type']}")
    else:
        lines.append(f"\n## K线形态\n  (无明显形态)")

    # ── 支撑与阻力 ──
    lines.append(f"\n## 支撑与阻力")
    lines.append(f"  {'支撑位':<10} {'来源':<8} {'强度'}")
    for s in sr.get("supports", []):
        lines.append(f"  {s['level']:<10} {s['source']:<8} {s['strength']}")
    lines.append(f"  {'阻力位':<10} {'来源':<8} {'强度'}")
    for r in sr.get("resistances", []):
        lines.append(f"  {r['level']:<10} {r['source']:<8} {r['strength']}")

    # ── 趋势结构 ──
    lines.append(f"\n## 趋势结构")
    lines.append(f"  波浪状态: {wave}")
    if box:
        lines.append(f"  箱体: {box['top']}-{box['bottom']} 震荡 (幅度{box['range_pct']}%, {box['days']}日)")
    if breakout and breakout.get("status", "未突破") != "未突破":
        lines.append(f"  突破: {breakout.get('status')}")

    # ── A 股特化 ──
    if limit_data:
        lines.append(f"\n## A股特化分析")
        lines.append(f"  板块制度: {limit_data.get('board', '-')} (涨跌停{limit_data.get('limit_ratio', 10)}%)")
        lines.append(f"  涨跌停价: 涨停{limit_data.get('limit_up_price', '-')} / 跌停{limit_data.get('limit_down_price', '-')}")
        lines.append(f"  当前状态: {limit_data.get('board_status', '-')}")
        if limit_data.get("limit_streak", 0) > 0:
            lines.append(f"  连板: {limit_data.get('limit_streak')}连板 ({limit_data.get('streak_type')})")
            if limit_data.get("streak_volume"):
                lines.append(f"  连板量能: {limit_data['streak_volume']}")
        if limit_data.get("t1_risk"):
            lines.append(f"  ⚠ {limit_data['t1_risk']}")

    # ── 综合建议止损 ──
    lines.append(f"\n## 仓位参考（技术面）")
    nearest_support = sr.get("nearest_support")
    if nearest_support:
        stop_pct = round((meta['price_num'] - nearest_support) / meta['price_num'] * 100, 1)
        lines.append(f"  止损位: {nearest_support} (距现价 -{abs(stop_pct)}%)")
    nearest_resistance = sr.get("nearest_resistance")
    if nearest_resistance:
        tp_pct = round((nearest_resistance - meta['price_num']) / meta['price_num'] * 100, 1)
        lines.append(f"  止盈位: {nearest_resistance} (距现价 +{tp_pct}%)")
    lines.append(f"  纯技术视角，不构成投资建议。需结合基本面、市场环境综合判断。")

    lines.append("═" * 72)
    return "\n".join(lines)


def render_quick(features, score, meta):
    """快速技术摘要。"""
    ma = features.get("ma_system", {})
    macd = features.get("macd") or {}
    vol = features.get("volume") or {}
    sr = features.get("support_resistance", {})
    limit_data = features.get("limit_analysis") or {}

    lines = []
    lines.append(f"## 技术面快扫: {meta['name']} ({meta['code']})")
    lines.append(f"现价: {meta['price']} | 涨跌: {meta['change_pct']}% | 板块: {meta['board']} | {meta['timestamp']}")
    lines.append("")
    lines.append(f"评分: {score['score']}/100 ({score['grade']})")
    lines.append(f"趋势: {ma.get('alignment', '-')}")
    macd_icon = "↑金叉" if macd.get('signal') == 1 else "↓死叉" if macd.get('signal') == -1 else "→"
    lines.append(f"MACD: {macd_icon} | {macd.get('bar_trend', '-')}")
    if macd.get("divergence"):
        lines.append(f"  ⚠ {macd['divergence']}")
    lines.append(f"量能: {vol.get('volume_ratio_desc', '-')} | {vol.get('volume_price', '-')}")
    lines.append(f"支撑: {sr.get('nearest_support', '-')} | 阻力: {sr.get('nearest_resistance', '-')}")
    if limit_data and limit_data.get("limit_streak", 0) > 0:
        lines.append(f"连板: {limit_data['limit_streak']}板 ({limit_data.get('board_status')})")
    if score["buy_signals"]:
        lines.append(f"买入: {', '.join(score['buy_signals'])}")
    if score["sell_signals"]:
        lines.append(f"卖出: {', '.join(score['sell_signals'])}")
    lines.append(f"⚠ 纯技术视角，不构成投资建议")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# L14: CLI
# ═══════════════════════════════════════════════════════════════

def _parse_records(records):
    """将 K 线数据转成数值列表。"""
    closes = [to_float(r.get("close")) for r in records if to_float(r.get("close")) > 0]
    opens = [to_float(r.get("open")) for r in records if to_float(r.get("open")) > 0]
    highs = [to_float(r.get("high")) for r in records if to_float(r.get("high")) > 0]
    lows = [to_float(r.get("low")) for r in records if to_float(r.get("low")) > 0]
    volumes = [to_float(r.get("volume")) for r in records if to_float(r.get("volume")) > 0]

    min_len = min(len(closes), len(opens), len(highs), len(lows), len(volumes))
    return closes[:min_len], opens[:min_len], highs[:min_len], lows[:min_len], volumes[:min_len]


def _compute_all(closes, opens, highs, lows, volumes, records, board, quote):
    """计算所有技术指标。"""
    features = {}

    features["ma_system"] = ma_system(closes)
    features["macd"] = macd_full(closes)
    features["kdj"] = kdj_full(closes, highs, lows)
    features["bollinger"] = bollinger(closes) or {}
    features["rsi"] = rsi_features(closes)
    features["volume"] = volume_analysis(closes, volumes) or {}
    features["patterns"] = detect_candle_patterns(records)
    features["support_resistance"] = support_resistance(closes, highs, lows, features["ma_system"])
    features["box"] = box_detection(highs, lows, closes)
    nearest_r = features["support_resistance"].get("nearest_resistance")
    features["breakout"] = breakout_check(closes, highs, volumes, nearest_r) if nearest_r else {}
    features["wave"] = wave_state(closes, highs, lows)
    features["limit_analysis"] = limit_analysis(records, board, quote)

    return features


def main():
    parser = argparse.ArgumentParser(description="A 股纯技术分析")
    parser.add_argument("code", help="证券代码，如 sh600989")
    parser.add_argument("--scale", "-s", type=int, default=240, help="K线周期: 240=日K, 60=60分钟, 30=30分钟, 15=15分钟, 5=5分钟")
    parser.add_argument("--quick", "-q", action="store_true", help="快速摘要模式")
    parser.add_argument("--json", "-j", action="store_true", help="JSON 输出")
    parser.add_argument("--datalen", type=int, default=250, help="K线数量（默认250）")
    args = parser.parse_args()

    code = normalize_quote_code(args.code)
    board = board_type(code)

    # 获取数据
    records = fetch_kline(code, args.scale, args.datalen)
    if not records:
        sys.exit(f"❌ 无法获取 {code} 的 K 线数据")

    quotes = fetch_batch([code])
    quote = quotes[0] if quotes else {}
    if not quote:
        sys.exit(f"❌ 无法获取 {code} 的实时行情")

    # 解析数值
    closes, opens, highs, lows, volumes = _parse_records(records)
    if len(closes) < 10:
        sys.exit(f"❌ {code} K 线数据不足（需≥10根，当前{len(closes)}）")

    # 计算所有指标
    features = _compute_all(closes, opens, highs, lows, volumes, records, board, quote)

    # 综合评分
    score = composite_score(features)

    # 元数据
    price_num = to_float(quote.get("price"))
    meta = {
        "code": code,
        "name": quote.get("name", ""),
        "price": quote.get("price", "-"),
        "price_num": price_num,
        "change_pct": quote.get("change_pct", "-"),
        "board": board,
        "scale": args.scale,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    # 查找止损位
    sr = features.get("support_resistance", {})
    nearest_support = sr.get("nearest_support")
    if nearest_support and price_num > 0:
        features["stop_loss_pct"] = round((price_num - nearest_support) / price_num * 100, 1)

    if args.json:
        output = {
            "meta": meta,
            "score": score,
            "features": {
                k: v for k, v in features.items()
                if k in ("ma_system", "macd", "kdj", "bollinger", "rsi", "volume",
                         "patterns", "support_resistance", "box", "breakout", "wave",
                         "limit_analysis")
            }
        }
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    elif args.quick:
        print(render_quick(features, score, meta))
    else:
        print(render_report(features, score, {}, meta))


if __name__ == "__main__":
    main()
