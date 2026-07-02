"""技术分析数据获取。

从 alert_engine.py 拆分，负责获取单只股票的行情、K 线、均线、MACD、支撑/阻力位。
"""

from data.helpers import fetch_quote_dict_or_none, fetch_kline_dicts
from technical.moving_average import ma_system
from technical.macd import macd_full
from technical.trend import support_resistance


def _fetch_technical_data(code: str, datalen: int = 120) -> dict:
    """获取单只股票的技术分析数据。

    Returns:
        {"quote": {...}, "kline": [...], "ma": {...}, "macd": {...}, "sr": {...}}
    """
    result = {"code": code, "quote": None, "error": None}

    # 实时行情
    try:
        result["quote"] = fetch_quote_dict_or_none(code)
    except Exception as e:
        result["error"] = f"行情获取失败: {e}"
        return result

    # K 线
    try:
        records = fetch_kline_dicts(code, scale=240, datalen=datalen)
    except Exception as e:
        result["error"] = f"K线获取失败: {e}"
        return result

    if not records or len(records) < 20:
        result["error"] = "K线数据不足"
        return result

    closes = [r["close"] for r in records]
    highs = [r["high"] for r in records]
    lows = [r["low"] for r in records]

    # 均线系统
    result["ma"] = ma_system(closes)

    # MACD
    result["macd"] = macd_full(closes)

    # 支撑/阻力位
    result["sr"] = support_resistance(closes, highs, lows, result["ma"])

    return result
