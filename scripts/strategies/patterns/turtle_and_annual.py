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


def detect_turtle_breakout(records, closes, highs, lows, volumes, entry=20, vol_ratio_min=1.5):
    """唐奇安通道突破：收盘突破前 entry 日最高价，且放量确认。

    海龟交易系统入场规则（20 日突破）；放量过滤剔除假突破。

    Args:
        records / closes / highs / lows / volumes: K 线数据
        entry: 突破通道窗口（默认 20）
        vol_ratio_min: 量比确认阈值（默认 1.5）

    Returns:
        signal dict 列表（结构同 ma_volume_strategy）。
    """
    signals = []
    n = len(closes)
    if n < entry + 2:
        return signals

    for i in range(entry, n):
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


def detect_annual_line_pullback(records, closes, highs, lows, volumes, period=250, pullback_max=0.12):
    """回踩年线企稳：价格自高点回撤到年线附近（±12%），且年线向上。

    长期趋势中的低吸形态：年线方向向上（趋势未破坏）+ 回踩不破年线。
    ±12% 容差对应 250 日均线本身的自然波动带，过窄会把真实回踩误判掉。

    Args:
        period: 年线周期（默认 250 交易日）
        pullback_max: 回踩范围（距年线最大偏离，默认 12%）

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
        # 回踩到年线 ±12% 范围内（对称容差：刚回踩到年线带即算，允许略破年线）
        dist = (closes[i] - ma_val) / ma_val
        if not (-pullback_max <= dist <= pullback_max):
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
