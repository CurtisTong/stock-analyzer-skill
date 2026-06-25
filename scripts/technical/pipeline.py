"""统一的技术指标计算管道。

为 StockAnalysisService 和 ScreeningService 提供共享的指标计算。
"""

import statistics


def compute_indicators(kline_bars: list, indicators: list[str] | None = None) -> dict:
    """统一的技术指标计算管道。

    Args:
        kline_bars: KlineBar 对象列表
        indicators: 要计算的指标列表，None 表示全部

    Returns:
        指标 dict
    """
    from technical import macd_full, rsi_features, volume_analysis

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
        ma10 = statistics.mean(closes[-10:])
        ma20 = (
            statistics.mean(closes[-20:])
            if len(closes) >= 20
            else statistics.mean(closes)
        )
        result["trend"] = (
            1 if closes[-1] > ma10 > ma20 else (-1 if closes[-1] < ma10 < ma20 else 0)
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

    return result
