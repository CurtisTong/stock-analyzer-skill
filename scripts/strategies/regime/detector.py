"""
市场 4 信号采集：从沪深 300 K 线衍生 4 类信号。
所有信号都基于 `sh000300` 日 K，避免拉多源数据。

v2.8: 增加成分股宽度 fallback（_compute_constituent_breadth）。
v2.9: index_trend 改用 tanh 平滑压缩（tanh(raw * 1.5)），避免 hard clamp
        时的方向反转与阶跃跳变；同时增加国家队 ETF 放量信号探测。
"""

import logging
import math
import statistics
from typing import Dict, Optional

from common import to_float
from data import get_kline
from config.loader import safe_get

logger = logging.getLogger(__name__)


def detect_signals(benchmark: str = "sh000300", window: int = 60) -> Dict[str, float]:
    """采集 4 类市场信号。

    Args:
        benchmark: 基准指数代码（默认沪深 300）
        window: 拉取 K 线根数（默认 60，约 1 季度）

    Returns:
        dict: {
            "index_trend": -1.0 ~ +1.0,  # 趋势强度（MA20 vs MA60 + 20日涨跌幅）
            "volatility": 0.0 ~ +∞,       # 20日年化波动率（%）
            "breadth": 0.0 ~ 1.0,         # 20日内阳线占比
            "turnover": 0.0 ~ +∞,         # 20日均成交额（亿元）
        }
        数据不足时所有信号返回 0.0
    """
    try:
        bars = get_kline(benchmark, scale=240, datalen=window)
    except Exception as e:
        logger.debug("获取基准 K 线失败 %s: %s", benchmark, e)
        return _zero_signals()

    if not bars or len(bars) < 20:
        return _zero_signals()

    return compute_signals_from_bars(bars)


def compute_signals_from_bars(bars) -> Dict[str, float]:
    """从已有 K 线列表计算 4 类信号（v2.8 新增）。

    与 detect_signals 的差异：信号源已存在（bars 列表），不依赖网络拉取；
    用于：
      - 测试场景（构造 bars 直接驱动）
      - 回测引擎（用指数 bars 而非实时拉取）
      - live path 内部复用

    v2.9 新增：成分股宽度 fallback、tanh 压缩、国家队 ETF 信号探测。

    Args:
        bars: K 线列表（最近的 bar 在末尾）

    Returns:
        dict: index_trend / volatility / breadth / turnover / national_team
    """
    if not bars or len(bars) < 20:
        return _zero_signals()

    closes = [b.close for b in bars if b.close > 0]
    if len(closes) < 20:
        return _zero_signals()

    # ---- 1. 指数趋势：MA20 vs MA60 + 20 日涨跌幅，v2.9 tanh 平滑压缩 ----
    ma20 = statistics.mean(closes[-20:])
    ma60 = statistics.mean(closes[-60:]) if len(closes) >= 60 else ma20
    trend_strength = (ma20 / ma60 - 1) * 10  # MA 偏离度 × 10
    ret20 = (closes[-1] / closes[-20] - 1) if closes[-20] > 0 else 0
    raw_trend = trend_strength + ret20 * 2
    # v2.9: tanh 压缩，避免 hard clamp 时的方向反转。scale=1.5 不改变阈值语义。
    tanh_scale = safe_get("regime.yaml", "thresholds.tanh_scale", 1.5)
    index_trend = math.tanh(raw_trend * tanh_scale)

    # ---- 2. 波动率：20 日日收益率 stdev × √252 ----
    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            returns.append((closes[i] - closes[i - 1]) / closes[i - 1])
    recent_returns = returns[-20:]
    daily_std = statistics.stdev(recent_returns) if len(recent_returns) >= 2 else 0
    annualized_vol = daily_std * (252**0.5) * 100  # 百分比

    # ---- 3. 市场宽度：v2.8 优先成分股宽度，否则 fallback 指数阳线占比 ----
    breadth = _compute_constituent_breadth(bars)
    if breadth is None:
        recent = recent_returns
        breadth = sum(1 for r in recent if r > 0) / len(recent) if recent else 0.5

    # ---- 4. 成交额：20 日均成交额（亿元）----
    recent_bars = bars[-20:] if len(bars) >= 20 else bars
    amounts_yi = [to_float(b.amount) / 1e8 for b in recent_bars if b.amount > 0]
    turnover = statistics.mean(amounts_yi) if amounts_yi else 0

    # v2.9: 国家队 ETF 放量信号（叠加 signals 用于追溯）
    national_team = _detect_national_team_signal(bars)

    return {
        "index_trend": round(index_trend, 4),
        "volatility": round(annualized_vol, 2),
        "breadth": round(breadth, 4),
        "turnover": round(turnover, 2),
        "national_team": national_team,
    }


def _compute_constituent_breadth(bars) -> Optional[float]:
    """v2.8: 计算 CSI300 成分股站上 MA20 的占比。

    优先尝试 breadth 模块（需 CSI300 成分股列表 + K 线拉取），失败返回 None，
    让调用方 fallback 到指数阳线占比。

    Returns:
        0.0 ~ 1.0，失败返回 None。
    """
    try:
        from . import breadth

        return breadth.compute_constituent_breadth(window=20)
    except Exception as e:
        logger.debug("成分股宽度计算失败，fallback 指数阳线占比: %s", e)
        return None


def _detect_national_team_signal(bars) -> bool:
    """v2.9: 国家队 ETF 放量信号探测（detector 内部版本）。

    委托给 national_team 模块；任何失败都返回 False（live 路径也会
    在 smoother 层再降级到 chip 保底）。

    Returns:
        True 当检测到任意 ETF 异常放量。
    """
    try:
        from .national_team import detect_national_team

        result = detect_national_team()
        return bool(result.get("detected", False))
    except Exception as e:
        logger.debug("国家队信号探测失败: %s", e)
        return False


def _zero_signals() -> Dict[str, float]:
    return {
        "index_trend": 0.0,
        "volatility": 0.0,
        "breadth": 0.5,
        "turnover": 0.0,
        "national_team": False,
    }
