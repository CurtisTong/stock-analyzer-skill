"""国家队 ETF 放量信号：日级 + 尾盘 5 分钟双粒度。

监测 510050/510300/510500 的异常放量，捕捉国家队入场迹象。
触发时 chip 因子权重至少保留 0.6（不全面弃用），因为国家队行为会扭曲筹码分布信号。

双粒度设计：
- 日级：当日 volume / 20 日均量 > 3x（捕捉全天异常放量）
- 尾盘：5 分钟 K 最后 6 根（30 分钟）volume / 前 18 根均量 > 2.5x（捕捉尾盘集中买入）
"""

import logging
import statistics
from typing import Dict

from common import to_float
from data import get_kline

logger = logging.getLogger(__name__)

NATIONAL_TEAM_ETFS = ["sh510050", "sh510300", "sh510500"]


def detect_national_team(
    daily_threshold: float = 3.0, tail_threshold: float = 2.5
) -> Dict:
    """检测国家队 ETF 放量。

    Args:
        daily_threshold: 日级放量倍数阈值（默认 3x）
        tail_threshold: 尾盘放量倍数阈值（默认 2.5x）

    Returns:
        {"detected": bool, "daily_spike": bool, "tail_spike": bool, "details": [...]}
    """
    daily_spike = False
    tail_spike = False
    details = []

    for code in NATIONAL_TEAM_ETFS:
        # 日级：当日 volume / 前 20 日均量 > threshold
        daily_bars = _safe_get_kline(code, scale=240, datalen=21)
        if daily_bars and len(daily_bars) >= 21:
            today_vol = to_float(daily_bars[-1].volume)
            base_vols = [
                to_float(b.volume) for b in daily_bars[-21:-1] if b.volume > 0
            ]
            if base_vols and today_vol > 0:
                base_avg = statistics.mean(base_vols)
                ratio = today_vol / base_avg if base_avg > 0 else 1.0
                if ratio >= daily_threshold:
                    daily_spike = True
                    details.append(f"{code} 日放量 {ratio:.1f}x")

        # 尾盘：5 分钟 K 最后 6 根（30 分钟）volume / 前 18 根均量 > threshold
        tail_bars = _safe_get_kline(code, scale=5, datalen=24)
        if tail_bars and len(tail_bars) >= 24:
            tail_vol = sum(to_float(b.volume) for b in tail_bars[-6:])
            base_tail = [
                to_float(b.volume) for b in tail_bars[-24:-6] if b.volume > 0
            ]
            if base_tail and tail_vol > 0:
                base_tail_avg = statistics.mean(base_tail) * 6  # 对齐窗口
                ratio = tail_vol / base_tail_avg if base_tail_avg > 0 else 1.0
                if ratio >= tail_threshold:
                    tail_spike = True
                    details.append(f"{code} 尾盘放量 {ratio:.1f}x")

    return {
        "detected": daily_spike or tail_spike,
        "daily_spike": daily_spike,
        "tail_spike": tail_spike,
        "details": details,
    }


def _safe_get_kline(code: str, scale: int, datalen: int):
    """安全获取 K 线，失败返回 None。"""
    try:
        return get_kline(code, scale=scale, datalen=datalen)
    except Exception as e:
        logger.debug("获取 %s K线失败: %s", code, e)
        return None
