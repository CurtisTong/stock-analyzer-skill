"""
4 状态分类器：基于 4 信号判定 bull / bear / range / panic。

判定规则（doc#03）：
  panic:  volatility >= 35 OR (turnover < 5000 AND index_trend < -0.3)
  bull:   index_trend > 0.3 AND breadth > 0.55
  bear:   index_trend < -0.2 AND breadth < 0.45
  range:  其他情况
"""

from enum import Enum
from typing import Dict


class RegimeState(str, Enum):
    BULL = "bull"
    BEAR = "bear"
    RANGE = "range"
    PANIC = "panic"

    @property
    def label(self) -> str:
        return {
            RegimeState.BULL: "牛市",
            RegimeState.BEAR: "熊市",
            RegimeState.RANGE: "震荡",
            RegimeState.PANIC: "冰点",
        }[self]


def classify_regime(signals: Dict[str, float]) -> RegimeState:
    """根据 4 信号判定市场状态。

    Args:
        signals: detect_signals() 输出

    Returns:
        RegimeState 枚举值
    """
    trend = signals.get("index_trend", 0)
    vol = signals.get("volatility", 0)
    breadth = signals.get("breadth", 0.5)
    turnover = signals.get("turnover", 0)

    # panic 优先：高波动 OR 极端缩量+大跌
    if vol >= 35 or (turnover > 0 and turnover < 5000 and trend < -0.3):
        return RegimeState.PANIC

    # bull：强趋势+宽度扩张
    if trend > 0.3 and breadth > 0.55:
        return RegimeState.BULL

    # bear：下跌趋势+宽度收缩
    if trend < -0.2 and breadth < 0.45:
        return RegimeState.BEAR

    return RegimeState.RANGE
