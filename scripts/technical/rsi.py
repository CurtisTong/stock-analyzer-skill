"""
RSI 指标（Wilder 平滑方法）。
无内部依赖。
"""


def _rsi_wilder(closes, period):
    """Wilder RSI 单周期计算。

    数据不足 period + 1 根时返回 None。

    v1.28.0：docstring 更正口径说明——本实现是 **Wilder 平滑**（分母用
    平均跌幅 avg_loss），与通达信/同花顺的 SMA(MAX(C-LC,0),N,1) /
    SMA(ABS(C-LC),N,1)（分母用**绝对涨跌**）不同。实测两者在 30/70 阈值上
    约 0.44% 的样本判定相反（用户会看到与第三方软件不同的结论），
    属已知口径差异，非缺陷。
    """
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
        # 全涨 → RSI 100；完全平坦（avg_gain 也 0）→ 中性 50，非超买
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def rsi_features(closes, period=14):
    """RSI 分析：主周期（默认 14）+ 6/12/24 三档参考。

    主键 rsi/signal/zone_desc 基于主周期 period 计算（与历史行为一致），
    附加 rsi6/rsi12/rsi24 供报告层展示多周期；数据不足的周期返回 None。
    """
    rsi = _rsi_wilder(closes, period)
    if rsi is None:
        return None

    rsi6 = _rsi_wilder(closes, 6)
    rsi12 = _rsi_wilder(closes, 12)
    rsi24 = _rsi_wilder(closes, 24)

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

    return {
        "rsi": round(rsi, 1),
        "rsi6": round(rsi6, 1) if rsi6 is not None else None,
        "rsi12": round(rsi12, 1) if rsi12 is not None else None,
        "rsi24": round(rsi24, 1) if rsi24 is not None else None,
        "signal": signal,
        "zone_desc": zone_desc,
    }
