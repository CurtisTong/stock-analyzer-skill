"""
市场状态引擎：4 状态 + 4 信号 + Overlay。

解决问题（doc#03 / review#3）：
  固定权重不随市场状态变化，导致策略在牛/熊/震荡/冰点下表现不稳定。
  本模块将 market_weights 节正式接入 6 因子加权管道。

4 状态：
  - bull    牛市：趋势跟随加权，估值降权
  - bear    熊市：质量+波动防御加权，动量降权
  - range   震荡：质量+估值均衡加权
  - panic   冰点：极度防御（高波动+高质量+低动量）

4 信号（全部从 sh000300 K 线衍生）：
  - index_trend   MA20 vs MA60 + 20 日涨跌幅
  - volatility    20 日年化波动率
  - breadth       20 日内阳线占比
  - turnover      20 日均成交额（亿元）

Overlay 输出 6 因子权重调节系数（1.0=不变）：
  调节后权重 = 原权重 × 调节系数 → 重新归一化到 1.0
"""

from .detector import detect_signals
from .classifier import classify_regime, RegimeState
from .overlay import compute_overlay_weights, OVERLAY_MATRIX

__all__ = [
    "detect_signals",
    "classify_regime",
    "compute_overlay_weights",
    "RegimeState",
    "OVERLAY_MATRIX",
]
