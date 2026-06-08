"""
波动率因子评分：基于历史收益率标准差，低波动得高分。
A 股低波动异象显著——低波动股票长期跑赢高波动股票。
"""
from common import clamp
from strategies.thresholds import get_industry_threshold


def _stdev(values):
    """计算标准差（纯 Python 实现，无需 statistics 模块）。"""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    return variance ** 0.5


def _vol_score(vol, vol_threshold):
    """根据波动率和阈值计算评分（低波动得高分）。"""
    if vol <= vol_threshold * 0.4:
        return 95  # 极低波动
    elif vol <= vol_threshold * 0.7:
        return 80  # 低波动
    elif vol <= vol_threshold:
        return 65  # 正常波动（偏稳）
    elif vol <= vol_threshold * 1.3:
        return 50  # 正常波动
    elif vol <= vol_threshold * 1.8:
        return 30  # 高波动
    elif vol <= vol_threshold * 2.5:
        return 15  # 很高波动
    else:
        return 5   # 极高波动


def volatility_score(kline_bars: list, industry: str = "默认") -> float:
    """波动率因子评分（行业差异化）。满分 100，低波动得高分。

    Args:
        kline_bars: K 线数据列表（至少 20 根），每根需有 close 属性
        industry: 行业名称，用于加载差异化阈值

    Returns:
        0-100 的评分，波动率越低得分越高
    """
    if len(kline_bars) < 20:
        return 50  # 数据不足，返回中性分

    # 计算 20 日日收益率标准差
    recent = kline_bars[-20:]
    returns = []
    for i in range(1, len(recent)):
        if recent[i - 1].close > 0:
            returns.append((recent[i].close - recent[i - 1].close) / recent[i - 1].close)

    if len(returns) < 10:
        return 50

    vol = _stdev(returns)
    vol_threshold = get_industry_threshold(industry, "vol_threshold", 0.025)
    return _vol_score(vol, vol_threshold)


def volatility_from_closes(closes: list, industry: str = "默认") -> float:
    """从收盘价列表计算波动率评分（兼容 screener 的 dict 数据）。

    Args:
        closes: 收盘价列表（至少 20 个）
        industry: 行业名称

    Returns:
        0-100 的评分
    """
    if len(closes) < 20:
        return 50

    recent = closes[-20:]
    returns = []
    for i in range(1, len(recent)):
        if recent[i - 1] > 0:
            returns.append((recent[i] - recent[i - 1]) / recent[i - 1])

    if len(returns) < 10:
        return 50

    vol = _stdev(returns)
    vol_threshold = get_industry_threshold(industry, "vol_threshold", 0.025)
    return _vol_score(vol, vol_threshold)
