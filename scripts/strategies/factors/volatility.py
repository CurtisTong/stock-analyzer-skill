"""
波动率因子评分：基于历史收益率标准差，低波动得高分。
A 股低波动异象显著——低波动股票长期跑赢高波动股票。
"""

from common import clamp
from strategies.thresholds import get_industry_threshold


def _stdev(values):
    """总体标准差（与 technical.core.stdev 一致，除以 n 而非 n-1）。"""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / n
    return variance**0.5


def _vol_score(vol, vol_threshold):
    """根据波动率和阈值计算评分。"""
    if vol <= vol_threshold * 0.4:
        return 95
    elif vol <= vol_threshold * 0.7:
        return 80
    elif vol <= vol_threshold:
        return 65
    elif vol <= vol_threshold * 1.3:
        return 50
    elif vol <= vol_threshold * 1.8:
        return 30
    elif vol <= vol_threshold * 2.5:
        return 15
    else:
        return 5


def _compute_vol_score(returns: list, industry: str) -> float:
    """从收益率序列计算波动率评分。"""
    if len(returns) < 10:
        return 50
    vol = _stdev(returns)
    vol_threshold = get_industry_threshold(industry, "vol_threshold", 0.025)
    return _vol_score(vol, vol_threshold)


def volatility_score(kline_bars: list, industry: str = "默认") -> float:
    """波动率因子评分（接受 KlineBar 对象列表）。

    review#8 修复：窗口从 20 根扩至 60 根（约 1 季度日线），降低噪声。
    """
    if len(kline_bars) < 20:
        return 50
    recent = kline_bars[-60:] if len(kline_bars) >= 60 else kline_bars
    returns = [
        (recent[i].close - recent[i - 1].close) / recent[i - 1].close
        for i in range(1, len(recent))
        if recent[i - 1].close > 0
    ]
    return _compute_vol_score(returns, industry)


def volatility_from_closes(closes: list, industry: str = "默认") -> float:
    """从收盘价列表计算波动率评分。

    review#8 修复：窗口从 20 根扩至 60 根。
    """
    if len(closes) < 20:
        return 50
    recent = closes[-60:] if len(closes) >= 60 else closes
    returns = [
        (recent[i] - recent[i - 1]) / recent[i - 1]
        for i in range(1, len(recent))
        if recent[i - 1] > 0
    ]
    return _compute_vol_score(returns, industry)
