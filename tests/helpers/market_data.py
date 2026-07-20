"""K 线/行情合成工厂。

替代原 tests/conftest.py 内的 _generate_trend / _generate_sideways 函数，
让合成逻辑可复用、可参数化。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal
import math


def _today_str(offset_days: int = 0) -> str:
    """返回相对今天的 ISO 日期字符串（YYYY-MM-DD）。"""
    return (datetime.now() + timedelta(days=offset_days)).strftime("%Y-%m-%d")


def generate_trend(
    direction: Literal["up", "down"],
    n: int,
    base_price: float = 10.0,
    end_offset_days: int = 0,
) -> list[dict]:
    """生成单调趋势 K 线序列（n 根）。

    direction='up' 时 close 单调上升；direction='down' 时单调下降。
    end_offset_days 控制最后一根 K 线的相对今天的偏移（0=今天）。
    """
    records = []
    price = base_price
    start_date = datetime.now() - timedelta(days=n + 5 + abs(end_offset_days))
    for i in range(n):
        if direction == "up":
            change = 0.3 + (i % 3) * 0.1
        else:
            change = -0.3 - (i % 3) * 0.1
        open_p = price
        close_p = round(price + change, 2)
        high_p = round(max(open_p, close_p) + 0.2, 2)
        low_p = round(min(open_p, close_p) - 0.2, 2)
        records.append(
            {
                "day": (start_date + timedelta(days=i)).strftime("%Y-%m-%d"),
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "volume": 1000 + i * 50,
            }
        )
        price = close_p
    return records


def generate_sideways(
    n: int, center: float = 10.0, amplitude: float = 0.5
) -> list[dict]:
    """生成横盘震荡 K 线（n 根，正弦波动）。"""
    records = []
    start_date = datetime.now() - timedelta(days=n + 5)
    for i in range(n):
        offset = amplitude * math.sin(i * 0.5)
        price = center + offset
        records.append(
            {
                "day": (start_date + timedelta(days=i)).strftime("%Y-%m-%d"),
                "open": round(price - 0.1, 2),
                "high": round(price + 0.3, 2),
                "low": round(price - 0.3, 2),
                "close": round(price + 0.1, 2),
                "volume": 1000 + (i % 5) * 100,
            }
        )
    return records


def fenxing_top() -> list[dict]:
    """5 根标准顶分型 K 线（先涨后跌）。"""
    return [
        {
            "day": _today_str(-30),
            "open": 10.0,
            "high": 10.5,
            "low": 9.8,
            "close": 10.3,
            "volume": 1000,
        },
        {
            "day": _today_str(-29),
            "open": 10.3,
            "high": 11.0,
            "low": 10.2,
            "close": 10.8,
            "volume": 1200,
        },
        {
            "day": _today_str(-28),
            "open": 10.8,
            "high": 11.5,
            "low": 10.6,
            "close": 11.2,
            "volume": 1500,
        },
        {
            "day": _today_str(-27),
            "open": 11.2,
            "high": 11.3,
            "low": 10.4,
            "close": 10.5,
            "volume": 1100,
        },
        {
            "day": _today_str(-26),
            "open": 10.5,
            "high": 10.7,
            "low": 10.0,
            "close": 10.1,
            "volume": 900,
        },
    ]


def fenxing_bottom() -> list[dict]:
    """5 根标准底分型 K 线（先跌后涨）。"""
    return [
        {
            "day": _today_str(-30),
            "open": 10.0,
            "high": 10.5,
            "low": 9.8,
            "close": 10.1,
            "volume": 1000,
        },
        {
            "day": _today_str(-29),
            "open": 10.1,
            "high": 10.2,
            "low": 9.3,
            "close": 9.5,
            "volume": 1200,
        },
        {
            "day": _today_str(-28),
            "open": 9.5,
            "high": 9.6,
            "low": 9.0,
            "close": 9.1,
            "volume": 1500,
        },
        {
            "day": _today_str(-27),
            "open": 9.1,
            "high": 10.0,
            "low": 9.2,
            "close": 9.9,
            "volume": 1100,
        },
        {
            "day": _today_str(-26),
            "open": 9.9,
            "high": 10.4,
            "low": 9.8,
            "close": 10.3,
            "volume": 900,
        },
    ]


def limit_up(prev_close: float = 10.0) -> dict:
    """生成涨停 K 线（涨幅 ~10%）。"""
    return {
        "day": _today_str(-1),
        "open": prev_close,
        "high": round(prev_close * 1.1, 2),
        "low": prev_close,
        "close": round(prev_close * 1.1, 2),
        "volume": 5000,
    }
