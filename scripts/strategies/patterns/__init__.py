"""
策略模式识别模块

包含：
- 三阴一阳战法（sanying.py）
- 老鸭头（laoyatou.py）
- 美人肩（meirenjian.py）
- 双针探底（shuangzhen.py）
- 涨停双响炮（zhangting.py）
- 断板反包（duanban.py）
- 底部首板（dibu_shouban.py）
- MA + 成交量组合策略（ma_volume_strategy.py）
- 本土战法顶层编排（detect_all_local_patterns）
"""

from dataclasses import dataclass

from .ma_volume_strategy import (
    detect_ma_volume_signal,
    backtest_strategy,
    get_strategy_params,
)
from .sanying import detect_sanying_yiyang
from .laoyatou import detect_laoyatou
from .meirenjian import detect_meirenjian
from .shuangzhen import detect_shuangzhen
from .zhangting import detect_zhangting
from .duanban import detect_duanban
from .dibu_shouban import detect_dibu_shouban
from .turtle_and_annual import detect_turtle_breakout, detect_annual_line_pullback
from .classic import detect_classic_patterns

# 形态展示位上限（v1.24.0 由 5 提升到 10：增设经典形态库后 5 位会挤掉多数形态）
PATTERN_DISPLAY_LIMIT = 10

__all__ = [
    "PatternInput",
    "detect_ma_volume_signal",
    "backtest_strategy",
    "get_strategy_params",
    "detect_sanying_yiyang",
    "detect_laoyatou",
    "detect_meirenjian",
    "detect_shuangzhen",
    "detect_zhangting",
    "detect_duanban",
    "detect_dibu_shouban",
    "detect_turtle_breakout",
    "detect_annual_line_pullback",
    "detect_classic_patterns",
    "detect_all_local_patterns",
]


@dataclass
class PatternInput:
    """detect_all_local_patterns 的参数封装（并行数组）。"""

    records: list
    closes: list
    highs: list
    lows: list
    volumes: list
    mas: dict
    code: str = ""


def detect_all_local_patterns(inp: PatternInput):
    """
    运行所有本土战法形态识别，返回汇总结果。

    Args:
        inp: PatternInput，封装 records/closes/highs/lows/volumes/mas/code

    Returns:
        {
            "patterns": [{"name": ..., "type": ..., "date": ..., "desc": ..., "confidence": ...}],
            "summary": "...",
            "count": N,
        }
    """
    records = inp.records
    closes = inp.closes
    highs = inp.highs
    lows = inp.lows
    volumes = inp.volumes
    mas = inp.mas
    code = inp.code
    all_patterns = []

    # 三阴一阳/三阳一阴
    all_patterns.extend(detect_sanying_yiyang(records, volumes, code))

    # 老鸭头
    all_patterns.extend(detect_laoyatou(records, closes, volumes, mas))

    # 美人肩
    all_patterns.extend(detect_meirenjian(records, closes, highs, lows, volumes, mas))

    # 双针探底
    all_patterns.extend(detect_shuangzhen(records, closes, lows, volumes))

    # 涨停双响炮
    all_patterns.extend(detect_zhangting(records, closes, volumes, code))

    # 断板反包
    all_patterns.extend(detect_duanban(records, closes, highs, lows, volumes, code))

    # 底部首板
    all_patterns.extend(detect_dibu_shouban(records, closes, highs, lows, volumes, code))

    # 海龟突破（唐奇安通道 + 放量确认）
    all_patterns.extend(detect_turtle_breakout(records, closes, highs, lows, volumes))

    # 回踩年线企稳（趋势低吸）
    all_patterns.extend(detect_annual_line_pullback(records, closes, highs, lows, volumes))

    # 经典 K 线形态库（v1.24.0：12 个单/双/三 K 形态）
    all_patterns.extend(detect_classic_patterns(records, closes))

    # 按时间排序（最新的在后）
    all_patterns.sort(key=lambda p: p["idx"])

    # 去重：同一日期同一形态只保留一次
    seen = set()
    deduped = []
    for p in all_patterns:
        key = (p["name"], p["date"])
        if key not in seen:
            seen.add(key)
            deduped.append(p)

    # 只看最近出现的（idx 最大的）
    # v1.24.0 展示位 5 → 10：增设经典形态库（13 个）后，最近 5 个上限会挤掉多数形态
    recent = deduped[-PATTERN_DISPLAY_LIMIT:] if len(deduped) > PATTERN_DISPLAY_LIMIT else deduped

    bullish = [p["name"] for p in recent if p["type"] == "看涨"]
    bearish = [p["name"] for p in recent if p["type"] == "看跌"]

    summary_parts = []
    if bullish:
        summary_parts.append(f"看涨形态: {', '.join(bullish)}")
    if bearish:
        summary_parts.append(f"看跌形态: {', '.join(bearish)}")
    summary = "; ".join(summary_parts) if summary_parts else "未检测到本土战法形态"

    return {
        "patterns": recent,
        "summary": summary,
        "count": len(recent),
        # 未截断的检测总数（含被展示上限丢弃的早期形态）
        "detected_count": len(deduped),
        # 阈值必须与展示位上限一致（v1.24.0 展示位 5 → 10，此处未同步导致 6-10 条时误报截断）
        "truncated": len(deduped) > 10,
    }
