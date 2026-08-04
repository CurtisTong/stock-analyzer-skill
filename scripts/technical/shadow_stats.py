"""影线占比聚合统计（庄股毛刺识别的核心原语）。

复用 candlestick._body_shadow 的影线计算逻辑（body/upper/lower/total），
但在窗口内聚合统计，量化"N根K线中长影线占比"。

庄股特征：影线占振幅主体（avg_shadow_ratio > 0.6）+ 实体小（avg_body_ratio < 0.3）。

依赖: 无（纯标准库）
"""

from common import to_float

_LONG_SHADOW_THRESHOLD = 0.6  # 长影线判定：影线占全振幅 > 60%


def shadow_ratio_stats(records, window=20):
    """计算窗口内影线占比统计。

    Args:
        records: KlineBar dict 列表（含 open/high/low/close）
        window: 回看窗口，默认 20 日

    Returns:
        dict: {
            "avg_shadow_ratio": float,   # 平均(上影+下影)/全振幅
            "avg_body_ratio": float,     # 平均实体/全振幅
            "long_shadow_count": int,    # 长影线天数（影线>60%振幅）
            "long_shadow_pct": float,    # 长影线占比%
            "avg_upper_ratio": float,    # 平均上影/全振幅
            "avg_lower_ratio": float,    # 平均下影/全振幅
        }
        数据不足时返回 None。
    """
    if not records or len(records) < 3:
        return None

    recent = records[-window:] if len(records) >= window else records

    shadow_ratios = []
    body_ratios = []
    upper_ratios = []
    lower_ratios = []
    long_shadow_count = 0

    for r in recent:
        o = to_float(r.get("open"))
        c = to_float(r.get("close"))
        h = to_float(r.get("high"))
        low = to_float(r.get("low"))

        total = h - low
        if total <= 0:
            continue  # 一字板，无振幅，跳过

        body = abs(c - o)
        upper = h - max(c, o)
        lower = min(c, o) - low
        shadow = upper + lower

        shadow_ratio = shadow / total
        body_ratio = body / total

        shadow_ratios.append(shadow_ratio)
        body_ratios.append(body_ratio)
        upper_ratios.append(upper / total)
        lower_ratios.append(lower / total)

        if shadow_ratio > _LONG_SHADOW_THRESHOLD:
            long_shadow_count += 1

    if not shadow_ratios:
        return None

    n = len(shadow_ratios)
    return {
        "avg_shadow_ratio": round(sum(shadow_ratios) / n, 3),
        "avg_body_ratio": round(sum(body_ratios) / n, 3),
        "long_shadow_count": long_shadow_count,
        "long_shadow_pct": round(long_shadow_count / n * 100, 1),
        "avg_upper_ratio": round(sum(upper_ratios) / n, 3),
        "avg_lower_ratio": round(sum(lower_ratios) / n, 3),
    }
