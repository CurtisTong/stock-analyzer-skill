"""
MACD 指标（含背离检测）。
依赖: core (_ema_series, _find_swing_points, _EPS)
"""

from .core import _ema_series, _find_swing_points, _EPS


def macd_full(closes):
    """MACD 完整分析：DIF/DEA/柱/金叉死叉 + 顶背离/底背离。"""
    if len(closes) < 34:
        return None

    # 计算 EMA 序列（ema12 比 ema26 多 14 个元素，需对齐）
    ema12_series = _ema_series(closes, 12)
    ema26_series = _ema_series(closes, 26)
    offset = len(ema12_series) - len(ema26_series)  # = 14
    dif_series = [ema12_series[offset + i] - ema26_series[i] for i in range(len(ema26_series))]

    # 当前值取序列末尾
    dif = dif_series[-1] if dif_series else 0.0

    dea_series = _ema_series(dif_series, 9)
    dea = dea_series[-1] if dea_series else dif
    prev_dif = dif_series[-2] if len(dif_series) >= 2 else dif
    # v1.28.0 修复：DEA 序列只有 1 个元素时（n=34，DEA 恰好起算），原实现把
    # prev_dea 回退到**当前** dea，而 prev_dif 取的是前一根 —— 金叉/死叉判定
    # 变成"前一根 DIF vs 当前 DEA"，坐标系错位。
    # 实测 n=34 时随机序列有 33/400 报出无意义的金叉/死叉。
    # 现在：DEA 不足 2 个元素 → 无前值可比 → 不判定金叉死叉（signal=0）。
    has_prev_dea = len(dea_series) >= 2
    # T8-b(P3)：无前值 DEA 时不再用当前 dif 冒充 prev_dea。
    # 原回退使 prev_bar=(prev_dif-dif)*2 实际衡量 DIF 自身涨跌，
    # 而非 DIF−DEA 柱变化，会输出伪造的"红柱放大/绿柱放大"。
    prev_dea = dea_series[-2] if has_prev_dea else None
    macd_bar = (dif - dea) * 2

    # 金叉死叉检测（使用 epsilon 避免浮点噪声；前值门控保持不变）
    signal = 0
    if has_prev_dea:
        if prev_dif < prev_dea - _EPS and dif > dea + _EPS:
            signal = 1
        elif prev_dif > prev_dea + _EPS and dif < dea - _EPS:
            signal = -1

    # 柱状图趋势：无前值 DEA 时只降级描述字段，不伪造 prev_bar；返回键保持不变
    if not has_prev_dea:
        bar_trend = "数据不足"
    else:
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
    if len(dif_series) < 60:
        return None

    # dif_series[i] 对应 closes[i + offset]（offset = EMA26 warmup = 25），
    # 即 dif_series 末尾对齐 closes 末尾，故 c 与 d 取相同末尾窗口一一对应
    lookback = min(60, len(dif_series))
    c = closes[-lookback:]
    d = dif_series[-lookback:]

    price_highs, price_lows = _find_swing_points(c, window=5)
    dif_highs, dif_lows = _find_swing_points(d, window=5)

    # 顶背离：价格新高而 DIF 未新高
    if len(price_highs) >= 2:
        last2_p = sorted(price_highs[-2:])
        if last2_p[1] - last2_p[0] >= 8:
            if c[last2_p[1]] > c[last2_p[0]]:
                # review §4.3-1（P2）：极值配对限定距离，避免跨很远 K 线误配。
                p0_dif = _nearest_point(dif_highs, last2_p[0], max_dist=5)
                p1_dif = _nearest_point(dif_highs, last2_p[1], max_dist=5)
                if p0_dif is not None and p1_dif is not None and p0_dif != p1_dif:
                    if d[p1_dif] < d[p0_dif]:
                        return "顶背离(看跌)"

    # 底背离：价格新低而 DIF 未新低
    if len(price_lows) >= 2:
        last2_p = sorted(price_lows[-2:])
        if last2_p[1] - last2_p[0] >= 8:
            if c[last2_p[1]] < c[last2_p[0]]:
                # review §4.3-1（P2）：与顶背离同口径，配对失败即不判背离。
                p0_dif = _nearest_point(dif_lows, last2_p[0], max_dist=5)
                p1_dif = _nearest_point(dif_lows, last2_p[1], max_dist=5)
                if p0_dif is not None and p1_dif is not None and p0_dif != p1_dif:
                    if d[p1_dif] > d[p0_dif]:
                        return "底背离(看涨)"

    return None


def _nearest_point(peaks, target, max_dist=None):
    """在极值点列表中找最近邻点索引。

    review §4.3-1（P2）：新增可选 max_dist（默认 None 保持旧调用兼容）。
    背离配对时传 5（与 _find_swing_points 的 window=5 对齐，与 volume.py
    的 OBV 背离 ≤5 窗口口径一致）；超出窗口视为配对失败 → 不判背离。
    """
    if not peaks:
        return None
    if max_dist is None:
        return min(peaks, key=lambda p: abs(p - target))
    candidates = [p for p in peaks if abs(p - target) <= max_dist]
    if not candidates:
        return None
    return min(candidates, key=lambda p: abs(p - target))
