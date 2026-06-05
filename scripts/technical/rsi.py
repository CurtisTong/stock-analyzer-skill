"""
RSI 指标。
无内部依赖。
"""
import statistics


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
