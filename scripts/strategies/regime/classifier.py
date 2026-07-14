"""
状态机分类器：v1 (4 状态) + v2.8 扩充（RANGE 细分）。

v1 4 状态：
  panic:  volatility >= 35 OR (turnover < 8000 AND index_trend < -0.3)
  bull:   index_trend > 0.3 AND breadth > 0.55
  bear:   index_trend < -0.2 AND breadth < 0.45
  range:  其他情况

v2.8 RANGE 细分（regime.yaml: choppy_vol_threshold=25）：
  range_low_vol:  非牛非熊 + vol < 25（低波震荡，维持动量）
  range_choppy:   非牛非熊 + vol >= 25（高波震荡，走防御）
  panic 优先于 bull/bear。

回测路径在 bars 不足时（<80 根）返回 RANGE_LOW_VOL，作为
"数据不足以判定"的合理降级——避免用不足信号误判为 panic/bull。
"""

from enum import Enum
from typing import Dict


class RegimeState(str, Enum):
    BULL = "bull"
    BEAR = "bear"
    RANGE = "range"
    RANGE_LOW_VOL = "range_low_vol"
    RANGE_CHOPPY = "range_choppy"
    PANIC = "panic"

    @property
    def label(self) -> str:
        return {
            RegimeState.BULL: "牛市",
            RegimeState.BEAR: "熊市",
            RegimeState.RANGE: "震荡",
            RegimeState.RANGE_LOW_VOL: "低波震荡",
            RegimeState.RANGE_CHOPPY: "高波震荡",
            RegimeState.PANIC: "冰点",
        }[self]


def classify_regime(signals: Dict[str, float]) -> RegimeState:
    """根据 4 信号判定市场状态。

    Args:
        signals: detect_signals() 输出

    Returns:
        RegimeState 枚举值（v2.8: RANGE 细分为 LOW_VOL/CHOPPY）
    """
    trend = signals.get("index_trend", 0)
    vol = signals.get("volatility", 0)
    breadth = signals.get("breadth", 0.5)
    turnover = signals.get("turnover", 0)

    # panic 优先：高波动 OR 极端缩量+大跌
    # A股日均成交额约 1-1.5 万亿（10000-15000亿元）
    if vol >= 35 or (turnover > 0 and turnover < 8000 and trend < -0.3):
        return RegimeState.PANIC

    # bull：强趋势+宽度扩张
    if trend > 0.3 and breadth > 0.55:
        return RegimeState.BULL

    # bear：下跌趋势+宽度收缩
    if trend < -0.2 and breadth < 0.45:
        return RegimeState.BEAR

    # v2.8: RANGE 细分（按 vol）
    return RegimeState.RANGE_CHOPPY if vol >= 25 else RegimeState.RANGE_LOW_VOL


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
