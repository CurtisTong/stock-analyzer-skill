"""
布林带分析。
依赖: core (sma, stddev)

2026-10-29 回测落地（indicator-env-backtest §5.2）："极度收窄=变盘"在低波动
蓝筹上不成立（茅台 11 次/招行 10 次收窄后 10 日绝对波动仅 3.4%，无变盘放大），
仅高波动股有效。bollinger 接受可选 highs/lows 计算 ATR%，低波动+极度收窄
时降级为"变盘信号弱"，消费方（signals/scoring）按 low_vol_squeeze 弱化。
"""

from .core import sma, stddev
from common.exceptions.silent_fallback import log_silent_fallback

# 低波动阈值：ATR/现价 < 2%（日均振幅）判为低波动，收窄变盘参考弱
_LOW_VOL_ATR_PCT = 0.02

# 首次触轨阈值（与下方 position_desc 的口径一致）
_UPPER_TOUCH_THRESHOLD = 0.9
_LOWER_TOUCH_THRESHOLD = 0.1


def _position_at(closes, idx, period, multiplier):
    """以 idx 为最新一根重算布林 position；idx 之前不足 period 根时返回 None。

    "首次触轨"需要判断前一根 position，但 bollinger 是纯函数、入参只有 closes，
    因此在函数内以 closes[:idx+1] 按同一 period/multiplier 重算前一根的
    mid/sd/upper/lower 与 position，避免依赖调用方传入历史 position。
    """
    if idx < period - 1:
        return None
    window = closes[idx + 1 - period : idx + 1]
    mid = sma(window, period)
    sd = stddev(window)
    upper = mid + multiplier * sd
    lower = mid - multiplier * sd
    if (upper - lower) <= 1e-6:
        return 0.5
    return (closes[idx] - lower) / (upper - lower)


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
        except Exception as exc:
            log_silent_fallback("boll.bollinger", exc)
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

    # ── 首次触轨事件（本轮首次穿越，而非同一趋势重复触发）──
    # 口径：当前 position 越过阈值，且前一根 position（以 closes[:-1] 为终点
    # 按同一 period/multiplier 重算）未越过同一阈值 → True；
    # 前一根也越过（同一趋势第二次触轨）或数据不足无法重算前一根 → False。
    # 仅新增字段，既有返回键保持不变（向后兼容旧调用方与回测脚本）。
    first_touch_upper = False
    first_touch_lower = False
    prev_position = _position_at(closes, len(closes) - 2, period, multiplier)
    if prev_position is not None:
        if position > _UPPER_TOUCH_THRESHOLD and prev_position <= _UPPER_TOUCH_THRESHOLD:
            first_touch_upper = True
        elif position < _LOWER_TOUCH_THRESHOLD and prev_position >= _LOWER_TOUCH_THRESHOLD:
            first_touch_lower = True

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
        # 首次触轨事件：本轮首次穿越上/下轨；重复触轨或数据不足为 False
        "first_touch_upper": first_touch_upper,
        "first_touch_lower": first_touch_lower,
    }
