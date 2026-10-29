"""海龟突破 + 回踩年线形态策略（v1.24.0 新增，对标 Sequoia-X/InStock）。

- detect_turtle_breakout：唐奇安通道 20 日真实突破（收盘价突破前 20 日最高）
  + 放量确认（量比 ≥ 1.5）。趋势跟踪经典入场型形态。
- detect_annual_line_pullback：回踩年线（MA250 或 200 日线）企稳，
  长期趋势中的低吸机会。

两者均返回与 ma_volume_strategy 一致的 signal dict，供
detect_all_local_patterns 统一编排。
"""

import sys
import os

scripts_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from common import to_float


def _ma(closes, period):
    """简单移动平均（长度不足返回 None）。"""
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def detect_turtle_breakout(records, closes, highs, lows, volumes, entry=20, exit_window=10, vol_ratio_min=1.5):
    """唐奇安通道突破：收盘突破前 entry 日最高价，且放量确认。

    海龟交易系统规则（经典版）：
    - 入场：20 日通道突破（收盘 > 前 20 日最高）
    - 出场：10 日通道跌破（收盘 < 前 10 日最低）
    - 仓位：按 ATR 风险比例（本模块只出形态信号，仓位由外部决定）

    放量过滤用于剔除假突破。退出信号只在**首次跌破**当日发出（连续跌破
    不重复报），与海龟"跌破即离场、重新突破才再入场"的语义一致。

    Args:
        records / closes / highs / lows / volumes: K 线数据
        entry: 入场通道窗口（默认 20）
        exit_window: 出场通道窗口（默认 10）
        vol_ratio_min: 量比确认阈值（默认 1.5）

    Returns:
        signal dict 列表（结构同 ma_volume_strategy）。
    """
    signals = []
    n = len(closes)
    if n < entry + 2:
        return signals

    for i in range(entry, n):
        # ── 出场信号：跌破 10 日通道（唐奇安下轨）──
        if i >= exit_window:
            donchian_low = min(lows[i - exit_window : i])
            prev_below = False
            if i - 1 >= exit_window:
                prev_donchian_low = min(lows[i - 1 - exit_window : i - 1])
                prev_below = closes[i - 1] < prev_donchian_low
            if closes[i] < donchian_low and not prev_below:
                signals.append(
                    {
                        "date": records[i].get("day", ""),
                        "idx": i,
                        "name": "海龟通道跌破",
                        "type": "看跌",
                        "conditions": [
                            f"跌破{exit_window}日通道低点({donchian_low:.2f})",
                            "海龟出场信号",
                        ],
                        "strength": 4,
                        "desc": f"收盘 {closes[i]:.2f} 跌破 {exit_window} 日唐奇安下轨（海龟出场）",
                        "confidence": "中",
                    }
                )

        donchian_high = max(highs[i - entry : i])
        if closes[i] <= donchian_high:
            continue
        # 放量确认：当日量 / 前 5 日均量
        avg_vol = sum(volumes[max(0, i - 5) : i]) / 5 if i >= 5 else 1.0
        vol_ratio = volumes[i] / avg_vol if avg_vol > 0 else 0.0
        if vol_ratio < vol_ratio_min:
            continue

        signal = {
            "date": records[i].get("day", ""),
            "idx": i,
            "name": "海龟突破",
            "type": "看涨",
            "conditions": [
                f"突破{entry}日通道高点({donchian_high:.2f})",
                f"放量{vol_ratio:.1f}x",
            ],
            "strength": 5 if vol_ratio >= 2.0 else 3,
            "desc": f"收盘 {closes[i]:.2f} 突破 {entry} 日唐奇安通道 + 放量确认",
            "confidence": "高" if vol_ratio >= 2.0 else "中",
        }
        signals.append(signal)
    return signals


def detect_annual_line_pullback(
    records, closes, highs, lows, volumes, period=250, pullback_max=0.12, pullback_over=0.03
):
    """回踩年线企稳：价格自高点回撤到年线附近，且年线向上。

    长期趋势中的低吸形态：年线方向向上（趋势未破坏）+ 回踩不破年线。

    容差口径：价格自上方回落至年线附近才算"回踩"，允许轻微跌破
    （-pullback_max）也允许刚站上年线一点点（+pullback_over）。
    原实现用对称容差（±pullback_max），价格**高于**年线 9.2% 也被判
    "回踩年线企稳"——那是上涨而非回踩，看涨形态存在系统性误报。

    Args:
        period: 年线周期（默认 250 交易日）
        pullback_max: 跌破年线的最大容差（默认 12%）
        pullback_over: 高于年线的最大容差（默认 3%，即刚站上年线也算企稳）

    Returns:
        signal dict 列表。
    """
    signals = []
    n = len(closes)
    if n < period + 3:
        return signals

    for i in range(period, n):
        ma_val = _ma(closes[: i + 1], period)
        if ma_val is None or ma_val <= 0:
            continue
        ma_prev = _ma(closes[:i], period)
        if ma_prev is None or ma_prev <= 0:
            continue
        # 年线需向上（趋势保持）
        if ma_val <= ma_prev:
            continue
        # 回踩到年线附近：允许轻微跌破，也允许刚站上年线一点点
        dist = (closes[i] - ma_val) / ma_val
        if not (-pullback_max <= dist <= pullback_over):
            continue
        # 近期有显著高点（回撤来自趋势高点，而非持续阴跌）
        recent_high = max(highs[max(period - 60, i - 60) : i + 1])
        drawdown = (closes[i] - recent_high) / recent_high if recent_high > 0 else 0.0
        if drawdown > -0.05:  # 从高点回撤不足 5%，不算"回踩"
            continue

        signal = {
            "date": records[i].get("day", ""),
            "idx": i,
            "name": "回踩年线",
            "type": "看涨",
            "conditions": [
                f"回踩年线(MA{period}={ma_val:.2f})",
                "年线向上",
            ],
            "strength": 4,
            "desc": f"回撤 {drawdown * 100:.1f}% 后于年线企稳（偏离 {dist * 100:+.1f}%）",
            "confidence": "中",
        }
        signals.append(signal)
    return signals
