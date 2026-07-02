"""
策略模式识别模块

包含：
- 三阴一阳战法（sanying.py）
- 老鸭头（laoyatou.py）
- 美人肩（meirenjian.py）
- 双针探底（shuangzhen.py）
- 涨停双响炮（zhangting.py）
- 底部首板（dibu_shouban.py）
- MA + 成交量组合策略（ma_volume_strategy.py）
- 本土战法顶层编排（detect_all_local_patterns）
"""

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
from .dibu_shouban import detect_dibu_shouban

__all__ = [
    "detect_ma_volume_signal",
    "backtest_strategy",
    "get_strategy_params",
    "detect_sanying_yiyang",
    "detect_laoyatou",
    "detect_meirenjian",
    "detect_shuangzhen",
    "detect_zhangting",
    "detect_dibu_shouban",
    "detect_all_local_patterns",
]


def detect_all_local_patterns(records, closes, highs, lows, volumes, mas, code=""):
    """
    运行所有本土战法形态识别，返回汇总结果。

    Args:
        records: K 线数据 list
        closes: 收盘价序列
        highs: 最高价序列
        lows: 最低价序列
        volumes: 成交量序列
        mas: 移动平均线 dict {"ma5": [...], "ma10": [...], "ma20": [...], "ma60": [...]}
        code: 股票代码（用于板块判断）

    Returns:
        {
            "patterns": [{"name": ..., "type": ..., "date": ..., "desc": ..., "confidence": ...}],
            "summary": "...",
            "count": N,
        }
    """
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

    # 底部首板
    all_patterns.extend(
        detect_dibu_shouban(records, closes, highs, lows, volumes, code)
    )

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
    recent = deduped[-5:] if len(deduped) > 5 else deduped

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
    }
