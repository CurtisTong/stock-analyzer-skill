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


def _classify_for_backtest(bars) -> RegimeState:
    """回测专用的 regime 分类器：直接用历史 K 线 bars 计算（不依赖网络）。

    复用了 detect_signals 的核心计算逻辑（trend/volatility/breadth/turnover），
    但数据源是 bars 列表（已存在的历史数据），而非 sh000300 的实时拉取。

    Args:
        bars: 已排序的历史 K 线列表（最近的 bar 在末尾）

    Returns:
        RegimeState 枚举值
    """
    from .detector import _zero_signals
    import statistics
    from common import to_float

    if not bars or len(bars) < 20:
        return classify_regime(_zero_signals())

    closes = [b.close for b in bars if b.close > 0]
    if len(closes) < 20:
        return classify_regime(_zero_signals())

    # 1. index_trend
    ma20 = statistics.mean(closes[-20:])
    ma60 = statistics.mean(closes[-60:]) if len(closes) >= 60 else ma20
    trend_strength = (ma20 / ma60 - 1) * 10
    ret20 = (closes[-1] / closes[-20] - 1) if closes[-20] > 0 else 0
    index_trend = max(-1.0, min(1.0, trend_strength + ret20 * 2))

    # 2. volatility
    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            returns.append((closes[i] - closes[i - 1]) / closes[i - 1])
    recent_returns = returns[-20:]
    daily_std = statistics.stdev(recent_returns) if len(recent_returns) >= 2 else 0
    annualized_vol = daily_std * (252**0.5) * 100

    # 3. breadth
    breadth = sum(1 for r in recent_returns if r > 0) / len(recent_returns)

    # 4. turnover
    recent_bars = bars[-20:]
    amounts_yi = [to_float(b.amount) / 1e8 for b in recent_bars if b.amount > 0]
    turnover = statistics.mean(amounts_yi) if amounts_yi else 0

    signals = {
        "index_trend": index_trend,
        "volatility": annualized_vol,
        "breadth": breadth,
        "turnover": turnover,
    }
    return classify_regime(signals)
