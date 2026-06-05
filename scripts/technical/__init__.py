"""
technical 包：A 股纯技术分析模块化包。

公开函数保持与原 technical.py 完全兼容。
"""
# 数学工具与数据解析
from .core import (
    sma,
    ema,
    _ema_series,
    stddev,
    _find_swing_points,
    _parse_records,
)

# 均线系统
from .moving_average import (
    ma_system,
    _MA_PERIODS,
)

# MACD
from .macd import (
    macd_full,
    _detect_macd_divergence,
)

# KDJ
from .kdj import kdj_full

# 布林带
from .boll import bollinger

# RSI
from .rsi import rsi_features

# 成交量
from .volume import (
    volume_analysis,
    _obv_series,
    _detect_obv_divergence,
)

# K 线形态
from .candlestick import (
    detect_candle_patterns,
    _body_shadow,
    _is_bullish,
    _candle_single,
    _candle_double,
    _candle_triple,
    _candle_ashare,
)

# 趋势结构
from .trend import (
    support_resistance,
    box_detection,
    breakout_check,
    wave_state,
)

# A 股特化
from .astock import (
    limit_analysis,
    _count_limit_streak,
)

# 综合评分
from .scoring import (
    composite_score,
    detect_market_environment,
    _market_weight_adjustments,
    _STOCK_TYPE_WEIGHTS,
)

# 买卖信号
from .signals import _generate_signals

# 报告渲染
from .report import (
    _fmt,
    render_report,
    render_quick,
)

__all__ = [
    # core
    "sma", "ema", "_ema_series", "stddev", "_find_swing_points", "_parse_records",
    # moving_average
    "ma_system", "_MA_PERIODS",
    # macd
    "macd_full", "_detect_macd_divergence",
    # kdj
    "kdj_full",
    # boll
    "bollinger",
    # rsi
    "rsi_features",
    # volume
    "volume_analysis", "_obv_series", "_detect_obv_divergence",
    # candlestick
    "detect_candle_patterns", "_body_shadow", "_is_bullish",
    "_candle_single", "_candle_double", "_candle_triple", "_candle_ashare",
    # trend
    "support_resistance", "box_detection", "breakout_check", "wave_state",
    # astock
    "limit_analysis", "_count_limit_streak",
    # scoring
    "composite_score", "detect_market_environment",
    "_market_weight_adjustments", "_STOCK_TYPE_WEIGHTS",
    # signals
    "_generate_signals",
    # report
    "_fmt", "render_report", "render_quick",
]
