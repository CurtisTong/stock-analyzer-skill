"""
市场 4 信号采集：从沪深 300 K 线衍生 4 类信号。
所有信号都基于 `sh000300` 日 K，避免拉多源数据。
"""

import logging
import statistics
from typing import Dict

from common import to_float
from data import get_kline

logger = logging.getLogger(__name__)


def detect_signals(benchmark: str = "sh000300", window: int = 60) -> Dict[str, float]:
    """采集 4 类市场信号。

    Args:
        benchmark: 基准指数代码（默认沪深 300）
        window: 拉取 K 线根数（默认 60，约 1 季度）

    Returns:
        dict: {
            "index_trend": -1.0 ~ +1.0,  # 趋势强度（MA20 vs MA60 + 20日涨跌幅）
            "volatility": 0.0 ~ +∞,       # 20日年化波动率（%）
            "breadth": 0.0 ~ 1.0,         # 20日内阳线占比
            "turnover": 0.0 ~ +∞,         # 20日均成交额（亿元）
        }
        数据不足时所有信号返回 0.0
    """
    try:
        bars = get_kline(benchmark, scale=240, datalen=window)
    except Exception as e:
        logger.debug("获取基准 K 线失败 %s: %s", benchmark, e)
        return _zero_signals()

    if not bars or len(bars) < 20:
        return _zero_signals()

    closes = [b.close for b in bars if b.close > 0]
    if len(closes) < 20:
        return _zero_signals()

    # ---- 1. 指数趋势：MA20 vs MA60 + 20 日涨跌幅 ----
    ma20 = statistics.mean(closes[-20:])
    ma60 = statistics.mean(closes[-60:]) if len(closes) >= 60 else ma20
    trend_strength = (ma20 / ma60 - 1) * 10  # MA 偏离度 × 10
    ret20 = (closes[-1] / closes[-20] - 1) if closes[-20] > 0 else 0
    index_trend = max(-1.0, min(1.0, trend_strength + ret20 * 2))

    # ---- 2. 波动率：20 日日收益率 stdev × √252 ----
    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            returns.append((closes[i] - closes[i - 1]) / closes[i - 1])
    recent_returns = returns[-20:]
    daily_std = statistics.stdev(recent_returns) if len(recent_returns) >= 2 else 0
    annualized_vol = daily_std * (252**0.5) * 100  # 百分比

    # ---- 3. 市场宽度：20 日内阳线占比 ----
    recent = returns[-20:] if len(returns) >= 20 else returns
    breadth = sum(1 for r in recent if r > 0) / len(recent) if recent else 0.5

    # ---- 4. 成交额：20 日均成交额（亿元）----
    # bars 中 amount 单位是元；转换为亿元
    recent_bars = bars[-20:] if len(bars) >= 20 else bars
    amounts_yi = [to_float(b.amount) / 1e8 for b in recent_bars if b.amount > 0]
    turnover = statistics.mean(amounts_yi) if amounts_yi else 0

    return {
        "index_trend": round(index_trend, 4),
        "volatility": round(annualized_vol, 2),
        "breadth": round(breadth, 4),
        "turnover": round(turnover, 2),
    }


def _zero_signals() -> Dict[str, float]:
    return {
        "index_trend": 0.0,
        "volatility": 0.0,
        "breadth": 0.5,
        "turnover": 0.0,
    }
