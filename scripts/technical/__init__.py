"""
technical 包：A 股纯技术分析模块化包。

公开函数保持与原 technical.py 完全兼容。
__all__ 仅包含公共 API；私有符号可通过 from technical.xxx import _yyy 导入。
"""

# 数学工具与数据解析
from .core import sma, ema, stddev

# 均线系统
from .moving_average import ma_system

# MACD
from .macd import macd_full

# KDJ
from .kdj import kdj_full

# 布林带
from .boll import bollinger

# RSI
from .rsi import rsi_features

# 成交量
from .volume import volume_analysis

# K 线形态
from .candlestick import detect_candle_patterns

# 趋势结构
from .trend import (
    support_resistance,
    box_detection,
    breakout_check,
    wave_state,
)

# A 股特化
from .astock import limit_analysis

# 综合评分
from .scoring import composite_score, detect_market_environment

# 报告渲染
from .report import render_report, render_quick

__all__ = [
    # core
    "sma",
    "ema",
    "stddev",
    # moving_average
    "ma_system",
    # macd
    "macd_full",
    # kdj
    "kdj_full",
    # boll
    "bollinger",
    # rsi
    "rsi_features",
    # volume
    "volume_analysis",
    # candlestick
    "detect_candle_patterns",
    # trend
    "support_resistance",
    "box_detection",
    "breakout_check",
    "wave_state",
    # astock
    "limit_analysis",
    # scoring
    "composite_score",
    "detect_market_environment",
    # report
    "render_report",
    "render_quick",
]
