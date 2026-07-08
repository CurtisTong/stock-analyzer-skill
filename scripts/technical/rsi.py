"""
RSI 指标（Wilder 平滑方法）。
无内部依赖。
"""


def rsi_features(closes, period=14):
    """RSI 计算（Wilder 指数平滑，与通达信/同花顺一致）。"""
    if len(closes) < period + 1:
        return None

    # 计算涨跌序列
    gains, losses = [], []
    for i in range(1, len(closes)):
        chg = closes[i] - closes[i - 1]
        gains.append(max(chg, 0))
        losses.append(max(-chg, 0))

    # Wilder 平滑：初始值用 SMA，后续用指数平滑
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - 100 / (1 + rs)

    signal = 0
    if rsi < 30:
        signal = 1
    elif rsi > 70:
        signal = -1

    # 区间描述（与 KDJ/BOLL 的 signal_desc/position_desc 风格一致）
    if rsi < 20:
        zone_desc = "极度超卖"
    elif rsi < 30:
        zone_desc = "超卖区"
    elif rsi < 40:
        zone_desc = "偏弱"
    elif rsi <= 60:
        zone_desc = "中性"
    elif rsi <= 70:
        zone_desc = "偏强"
    elif rsi <= 80:
        zone_desc = "超买区"
    else:
        zone_desc = "极度超买"

    return {"rsi": round(rsi, 1), "signal": signal, "zone_desc": zone_desc}
