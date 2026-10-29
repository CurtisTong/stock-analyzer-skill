"""
布林带分析。
依赖: core (sma, stddev)

2026-10-29 回测落地（indicator-env-backtest §5.2）："极度收窄=变盘"在低波动
蓝筹上不成立（茅台 11 次/招行 10 次收窄后 10 日绝对波动仅 3.4%，无变盘放大），
仅高波动股有效。bollinger 接受可选 highs/lows 计算 ATR%，低波动+极度收窄
时降级为"变盘信号弱"，消费方（signals/scoring）按 low_vol_squeeze 弱化。
"""

from .core import sma, stddev

# 低波动阈值：ATR/现价 < 2%（日均振幅）判为低波动，收窄变盘参考弱
_LOW_VOL_ATR_PCT = 0.02


def bollinger(closes, period=20, multiplier=2.0, highs=None, lows=None):
    """布林带分析：上/中/下轨 + 带宽 + 价格位置。

    Args:
        closes: 收盘价序列
        period: 布林带周期（默认 20）
        multiplier: 标准差倍数（默认 2.0）
        highs/lows: 最高/最低价序列（可选）。提供时按 ATR% 判定个股低波动，
            低波动+极度收窄降级为"变盘信号弱"；不提供时保持原语义
            （low_vol_squeeze=False，兼容旧调用方与回测脚本）。
    """
    if len(closes) < period:
        return None

    mid = sma(closes, period)
    sd = stddev(closes[-period:])
    upper = mid + multiplier * sd
    lower = mid - multiplier * sd
    bandwidth = (upper - lower) / mid if mid > 0 else 0
    last = closes[-1]
    position = (last - lower) / (upper - lower) if (upper - lower) > 1e-6 else 0.5

    # 个股波动特征（ATR%）：仅供"极度收窄"档位的变盘强度判定
    low_vol_squeeze = False
    if highs is not None and lows is not None and len(highs) == len(closes) and len(lows) == len(closes):
        try:
            from .volatility import compute_atr

            atr = compute_atr(highs, lows, closes)
            atr_pct = atr / last if last > 0 else 0.0
            if atr_pct > 0 and atr_pct < _LOW_VOL_ATR_PCT:
                low_vol_squeeze = True
        except Exception:
            low_vol_squeeze = False

    # 带宽状态（SKILL 声明"开口/收口"：开口 = 波动放大）
    if bandwidth >= 0.15:
        bw_desc = "开口(波动放大)"
    elif bandwidth < 0.05:
        # 回测证据：低波动股收窄后无变盘放大（茅台/招行 10 日绝对波动 3.4%），
        # 只有高波动股（宁德 10.3%）变盘参考价值；低波动时降级
        bw_desc = "极度收窄(低波动,变盘信号弱)" if low_vol_squeeze else "极度收窄(变盘信号)"
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
        # 变盘语义：带宽 < 0.05；low_vol_squeeze 表示因个股低波动而降级
        "squeeze": bandwidth < 0.05,
        "low_vol_squeeze": low_vol_squeeze,
    }
