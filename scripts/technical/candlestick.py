"""
K 线形态识别。
依赖: core (to_float via common)
"""

from common import to_float


def detect_candle_patterns(records):
    """识别最近 4 根 K 线的形态。"""
    if len(records) < 4:
        return []

    patterns = []
    bars = []
    for r in records[-4:]:
        bars.append(
            {
                "open": to_float(r.get("open")),
                "high": to_float(r.get("high")),
                "low": to_float(r.get("low")),
                "close": to_float(r.get("close")),
                "date": r.get("day", ""),
            }
        )

    # 单根形态（最近3根）
    for i, b in enumerate(bars[-3:]):
        idx = len(bars) - 3 + i
        prev_close = bars[idx - 1]["close"] if idx > 0 else b["open"]
        singles = _candle_single(b, prev_close)
        for s in singles:
            patterns.append(
                {"date": b["date"], "type": s, "position": f"T-{len(bars)-1-idx}"}
            )

    # A 股特化形态
    if len(bars) >= 2:
        ah = _candle_ashare(bars[-2], bars[-1])
        if ah:
            patterns.append({"date": bars[-1]["date"], "type": ah, "position": "T-0"})

    # 双根组合
    if len(bars) >= 2:
        doubles = _candle_double(bars[-2], bars[-1])
        for d in doubles:
            patterns.append({"date": bars[-1]["date"], "type": d, "position": "T-1~0"})

    # 三根组合
    if len(bars) >= 3:
        triples = _candle_triple(bars[-3], bars[-2], bars[-1])
        for t in triples:
            patterns.append({"date": bars[-1]["date"], "type": t, "position": "T-2~0"})

    return patterns


def _body_shadow(bar):
    """计算实体、上影线、下影线。"""
    body = abs(bar["close"] - bar["open"])
    upper_shadow = bar["high"] - max(bar["close"], bar["open"])
    lower_shadow = min(bar["close"], bar["open"]) - bar["low"]
    total = bar["high"] - bar["low"]
    return body, upper_shadow, lower_shadow, total


def _is_bullish(bar):
    return bar["close"] > bar["open"]


def _candle_single(bar, prev_close):
    """单根 K 线形态识别。"""
    body, upper, lower, total = _body_shadow(bar)
    if total <= 0:
        return []
    patterns = []

    # 十字星
    if body / total < 0.1:
        patterns.append("十字星(变盘信号)")
    # 锤子线
    elif lower > 2 * body and (bar["high"] - bar["close"]) < body:
        patterns.append("锤子线(底部反转)")
    # 倒锤子
    elif upper > 2 * body and (bar["close"] - bar["low"]) < body:
        patterns.append("倒锤子(可能见顶)")
    # 光头光脚阳线（浮点容差比较）
    elif (
        _is_bullish(bar)
        and abs(bar["close"] - bar["high"]) / max(bar["high"], 0.01) < 0.001
        and abs(bar["open"] - bar["low"]) / max(bar["low"], 0.01) < 0.001
    ):
        patterns.append("光头光脚阳线(强势)")
    # 光头光脚阴线（浮点容差比较）
    elif (
        not _is_bullish(bar)
        and abs(bar["open"] - bar["high"]) / max(bar["high"], 0.01) < 0.001
        and abs(bar["close"] - bar["low"]) / max(bar["low"], 0.01) < 0.001
    ):
        patterns.append("光头光脚阴线(弱势)")
    # T 字线
    elif body / total < 0.05 and upper < body and lower > 3 * body:
        patterns.append("T字线(下方支撑强)")
    # 倒 T 字
    elif body / total < 0.05 and lower < body and upper > 3 * body:
        patterns.append("倒T字(上方压力大)")

    return patterns


def _candle_ashare(prev, curr):
    """A 股特化形态。"""
    if _is_bullish(curr):
        if curr["close"] < prev["close"]:
            return "假阳真阴(收阳但实际下跌)"
    else:
        if curr["close"] > prev["close"]:
            return "假阴真阳(收阴但实际上涨)"
    return None


def _candle_double(b1, b2):
    """双根 K 线组合。"""
    patterns = []
    # 阳包阴
    if (
        not _is_bullish(b1)
        and _is_bullish(b2)
        and b2["close"] > b1["open"]
        and b2["open"] < b1["close"]
    ):
        patterns.append("阳包阴(看涨吞没)")
    # 阴包阳
    if (
        _is_bullish(b1)
        and not _is_bullish(b2)
        and b2["close"] < b1["open"]
        and b2["open"] > b1["close"]
    ):
        patterns.append("阴包阳(看跌吞没)")
    # 平底/平顶
    if abs(b1["low"] - b2["low"]) / max(b1["low"], 0.01) < 0.005:
        patterns.append("平底(支撑确认)")
    if abs(b1["high"] - b2["high"]) / max(b1["high"], 0.01) < 0.005:
        patterns.append("平顶(压力确认)")
    # 揉搓线：一长上影一长下影
    body1, upper1, lower1, _ = _body_shadow(b1)
    body2, upper2, lower2, _ = _body_shadow(b2)
    if (upper1 > 2 * body1 and lower2 > 2 * body2) or (
        lower1 > 2 * body1 and upper2 > 2 * body2
    ):
        patterns.append("揉搓线(洗盘或变盘)")
    return patterns


def _candle_triple(b1, b2, b3):
    """三根 K 线组合。"""
    patterns = []
    body1, _, _, _ = _body_shadow(b1)
    body2, _, _, _ = _body_shadow(b2)
    body3, _, _, _ = _body_shadow(b3)

    # 早晨之星：阴线 + 小实体 + 阳线
    if (
        not _is_bullish(b1)
        and body2 < body1 * 0.5
        and _is_bullish(b3)
        and b3["close"] > (b1["open"] + b1["close"]) / 2
    ):
        patterns.append("早晨之星(底部反转)")
    # 黄昏之星：阳线 + 小实体 + 阴线
    if (
        _is_bullish(b1)
        and body2 < body1 * 0.5
        and not _is_bullish(b3)
        and b3["close"] < (b1["open"] + b1["close"]) / 2
    ):
        patterns.append("黄昏之星(顶部反转)")
    # 红三兵
    if (
        _is_bullish(b1)
        and _is_bullish(b2)
        and _is_bullish(b3)
        and b1["close"] < b2["close"] < b3["close"]
    ):
        if b2["open"] > b1["open"] and b3["open"] > b2["open"]:
            patterns.append("红三兵(强势延续)")
    # 三只乌鸦
    if (
        not _is_bullish(b1)
        and not _is_bullish(b2)
        and not _is_bullish(b3)
        and b1["close"] > b2["close"] > b3["close"]
    ):
        patterns.append("三只乌鸦(弱势延续)")
    return patterns
