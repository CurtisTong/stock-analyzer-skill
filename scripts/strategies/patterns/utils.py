"""
本土战法形态识别工具函数。

注意：_sma/_ema 返回序列 list，与 technical/core.py 的 sma/ema（返回单值）签名不同，
不要合并，保持独立实现。
"""


def _sma(values, period):
    """简单移动平均。"""
    if len(values) < period:
        return []
    result = []
    for i in range(period - 1, len(values)):
        result.append(sum(values[i - period + 1 : i + 1]) / period)
    return result


def _ema(values, period):
    """指数移动平均。"""
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    result = [sum(values[:period]) / period]
    for v in values[period:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def _is_bearish(open_p, close_p):
    """阴线：收盘低于开盘。"""
    return close_p < open_p


def _is_bullish(open_p, close_p):
    """阳线：收盘高于开盘。"""
    return close_p >= open_p


def _lower_shadow(open_p, close_p, low_p):
    """下影线长度/实体比例。"""
    body_low = min(open_p, close_p)
    shadow = body_low - low_p
    body = abs(close_p - open_p)
    return shadow / max(body, 0.001)


def _upper_shadow(open_p, close_p, high_p):
    """上影线长度/实体比例。"""
    body_high = max(open_p, close_p)
    shadow = high_p - body_high
    body = abs(close_p - open_p)
    return shadow / max(body, 0.001)


def _body_pct(open_p, close_p):
    """实体涨跌幅百分比。"""
    return (close_p - open_p) / max(open_p, 0.001) * 100


def _is_limit_up(open_p, close_p, prev_close, board):
    """检测涨停（考虑板块涨跌幅限制）。"""
    limit_ratio = {"主板": 9.5, "创业板": 19.5, "科创板": 19.5, "北交所": 29.5}.get(
        board, 9.5
    )
    chg = (close_p - prev_close) / max(prev_close, 0.001) * 100
    return chg >= limit_ratio * 0.95
