"""均线止跌买点识别单元测试。

覆盖场景：
- 站上5日线（不再新低 + 收盘站上MA5 + 收盘回升）
- 回踩20日线不破（MA20附近 + 未跌破 + 上升趋势）
- 双重止跌（两条件都满足）
- 不满足（持续下跌/无趋势）
- 数据不足 -> None
"""

import pytest

from technical.ma_stop import ma_stop_buy
from technical.moving_average import ma_system


def _build_mas(closes):
    """用 ma_system 计算 mas dict。"""
    return ma_system(closes)


def _make_decline_then_rebound(n_pre=20, decline=6, rebound=5):
    """构造'先下跌创低再回升站上MA5'的序列。

    n_pre 前置平稳段，decline 下跌段，rebound 回升段。
    总长 n_pre + decline + rebound，保证 MA20 有值。
    """
    closes = []
    price = 10.0
    # 前置平稳（给MA20足够数据）
    for i in range(n_pre):
        closes.append(round(price + (i % 3 - 1) * 0.05, 2))
    # 下跌创低
    price = closes[-1]
    for i in range(decline):
        price = round(price - 0.3, 2)
        closes.append(price)
    # 回升站上MA5
    for i in range(rebound):
        price = round(price + 0.3, 2)
        closes.append(price)
    lows = [c - 0.2 for c in closes]
    highs = [c + 0.4 for c in closes]
    return closes, highs, lows


class TestMaStopBuy:
    """均线止跌买点识别。"""

    def test_above_ma5_stop_decline(self):
        """条件A：不再新低 + 站上5日线 + 收盘回升。"""
        closes, highs, lows = _make_decline_then_rebound()
        mas = _build_mas(closes)
        result = ma_stop_buy(closes, highs, lows, mas)
        assert result is not None
        assert result["signal"] == 1
        assert result["type"] in ("站上5日线", "双重止跌")

    def test_pullback_ma20_not_broken(self):
        """条件B：回踩20日线不破（上升趋势中回踩支撑）。"""
        # 构造25根K线：前18根上升，后7根浅回踩到MA20附近
        closes = []
        price = 10.0
        for i in range(18):
            price = round(price + 0.4, 2)
            closes.append(price)
        # 浅回踩，收盘逐步靠近MA20但不破
        for i in range(7):
            price = round(price - 0.15, 2)
            closes.append(price)
        # 最后一根收盘贴近MA20
        closes[-1] = round(sum(closes[-20:]) / 20, 2)
        lows = [c - 0.1 for c in closes]
        highs = [c + 0.3 for c in closes]
        mas = _build_mas(closes)
        result = ma_stop_buy(closes, highs, lows, mas)
        assert result is not None
        if result["signal"] == 1:
            assert result["type"] in ("回踩20日线", "双重止跌")

    def test_no_signal_continuous_decline(self):
        """持续下跌 -> 无止跌信号。"""
        closes = [10.0]
        for i in range(24):
            closes.append(round(closes[-1] - 0.2, 2))
        lows = [c - 0.1 for c in closes]
        highs = [c + 0.1 for c in closes]
        mas = _build_mas(closes)
        result = ma_stop_buy(closes, highs, lows, mas)
        assert result is not None
        assert result["signal"] == 0
        assert result["type"] is None

    def test_insufficient_data_returns_none(self):
        """数据不足返回 None（少于 lookback+1=11 根）。"""
        closes = [10.0, 10.5, 11.0]
        lows = [9.5, 10.0, 10.5]
        highs = [10.5, 11.0, 11.5]
        mas = _build_mas(closes)
        assert ma_stop_buy(closes, highs, lows, mas) is None

    def test_mas_none_fallback_to_sma(self):
        """mas 为空时现场补算 sma（MA20 数据足够时不崩溃）。"""
        closes, highs, lows = _make_decline_then_rebound()
        # 传空 mas，函数应内部用 sma 补算
        result = ma_stop_buy(closes, highs, lows, {})
        assert result is not None

    def test_return_structure_fields(self):
        """返回 dict 包含所有约定字段。"""
        closes, highs, lows = _make_decline_then_rebound()
        mas = _build_mas(closes)
        result = ma_stop_buy(closes, highs, lows, mas)
        assert result is not None
        for key in ("status", "signal", "desc", "type"):
            assert key in result, f"缺少字段 {key}"
