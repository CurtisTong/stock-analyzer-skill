"""统一的技术指标计算管道。

为 StockAnalysisService 和 ScreeningService 提供共享的指标计算。
复用 technical 包的指标函数，避免重复实现导致不一致。
"""

import statistics

from common import to_float
from technical.moving_average import ma_system
from technical.macd import macd_full
from technical.rsi import rsi_features
from technical.volume import volume_analysis


def compute_indicators(kline_bars: list, indicators: list[str] | None = None) -> dict:
    """统一的技术指标计算管道。

    Args:
        kline_bars: KlineBar 对象列表
        indicators: 要计算的指标列表，None 表示全部

    Returns:
        指标 dict
    """
    # 统一过滤：整条记录的 close 和 volume 都 > 0 才保留，确保数组对齐
    valid_bars = [b for b in kline_bars if b.close > 0 and b.volume > 0]
    closes = [b.close for b in valid_bars]
    volumes = [b.volume for b in valid_bars]

    if len(closes) < 10:
        return {
            "trend": 0,
            "ret20": 0,
            "rsi": 50,
            "macd_signal": 0,
            "vol_price_signal": 0,
            "closes": closes,
        }

    all_indicators = indicators is None
    result = {"closes": closes}

    if all_indicators or "trend" in indicators:
        # 复用 ma_system 的 MA10/MA20，避免重复计算
        ma_info = ma_system(closes)
        ma10 = ma_info.get("ma10")
        ma20 = ma_info.get("ma20")
        if ma10 is not None and ma20 is not None:
            result["trend"] = (
                1
                if closes[-1] > ma10 > ma20
                else (-1 if closes[-1] < ma10 < ma20 else 0)
            )
        else:
            # 数据不足时回退到简单计算
            ma10 = statistics.mean(closes[-10:])
            ma20 = (
                statistics.mean(closes[-20:])
                if len(closes) >= 20
                else statistics.mean(closes)
            )
            result["trend"] = (
                1
                if closes[-1] > ma10 > ma20
                else (-1 if closes[-1] < ma10 < ma20 else 0)
            )
        result["ma10"] = ma10
        result["ma20"] = ma20

    if all_indicators or "ret20" in indicators:
        base = closes[-21] if len(closes) >= 21 else closes[0]
        result["ret20"] = (closes[-1] / base - 1) * 100 if base else 0

    if all_indicators or "volume" in indicators:
        recent_vol = statistics.mean(volumes[-5:]) if len(volumes) >= 5 else 0
        base_vol = (
            statistics.mean(volumes[-20:-5]) if len(volumes) >= 20 else recent_vol
        )
        result["volume_ratio"] = recent_vol / base_vol if base_vol else 1

    if all_indicators or "rsi" in indicators:
        rsi_data = rsi_features(closes) or {}
        result["rsi"] = round(rsi_data.get("rsi", 50), 1)
        result["rsi_signal"] = rsi_data.get("signal", 0)

    if all_indicators or "macd" in indicators:
        macd = macd_full(closes) or {}
        result["macd_signal"] = macd.get("signal", 0)

    if all_indicators or "vol_price" in indicators:
        vp = volume_analysis(closes, volumes) or {}
        result["vol_price_signal"] = vp.get("volume_price_signal", 0)

    # (#6) Amihud 非流动性指标：mean(|daily_return| / amount) 近 20 日
    # 高值 = 流动性差（单位成交额引起的价格变动大）
    if all_indicators or "amihud" in indicators:
        amounts = [to_float(getattr(b, "amount", 0)) for b in valid_bars]
        result["amihud_illiq"] = _calc_amihud(closes, amounts)

    return result


def _calc_amihud(closes: list, amounts: list, window: int = 20) -> float:
    """(#6) 计算 Amihud 非流动性指标。

    illiq = mean(|r_i| / amount_i) for i in last `window` days
    其中 r_i = (close_i - close_{i-1}) / close_{i-1}

    Args:
        closes: 收盘价序列
        amounts: 成交额序列（元）
        window: 计算窗口（默认 20 日）

    Returns:
        Amihud 非流动性指标，数据不足返回 0
    """
    if len(closes) < 2 or len(amounts) < 2:
        return 0.0

    # 取最近 window 日的收益率和成交额
    n = min(window, len(closes) - 1)
    illiq_values = []
    for i in range(len(closes) - n, len(closes)):
        if i <= 0:
            continue
        try:
            prev_close = float(closes[i - 1])
            cur_close = float(closes[i])
            cur_amount = float(amounts[i])
        except (TypeError, ValueError):
            continue
        if prev_close <= 0 or cur_amount <= 0:
            continue
        ret = abs((cur_close - prev_close) / prev_close)
        illiq_values.append(ret / cur_amount)

    if not illiq_values:
        return 0.0

    return sum(illiq_values) / len(illiq_values)
