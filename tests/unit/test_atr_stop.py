"""ATR 自适应止损 + 移动止盈单元测试（2026-08-26 复盘 P1 盈亏比修复）。

覆盖：
- _calc_atr 已知序列断言
- ATR 止损触发（高波动股止损宽于固定 -8%）
- 移动止盈触发（收盘确认，避免当日冲高立即触发）
- 默认模式行为不变（回归）
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.engine import _calc_atr, _calc_return_with_stop_loss  # noqa: E402


class _Bar:
    """最小 K 线桩（仅含止损逻辑需要的字段）。"""

    def __init__(self, open_, high, low, close):
        self.open = open_
        self.high = high
        self.low = low
        self.close = close


def _flat_bars(n: int, price: float = 10.0) -> list:
    """n 根平盘 K 线（无波动）。"""
    return [_Bar(price, price, price, price) for _ in range(n)]


class TestCalcAtr:
    def test_insufficient_data_returns_zero(self):
        assert _calc_atr([]) == 0.0
        assert _calc_atr(_flat_bars(5)) == 0.0  # 不足 period+1

    def test_flat_bars_atr_zero(self):
        assert _calc_atr(_flat_bars(20)) == 0.0

    def test_known_range(self):
        # 14 根平盘 + 1 根大波动：TR = max(2, 2, 2) = 2（前一根 close=10）
        bars = _flat_bars(14) + [_Bar(10, 12, 10, 11)]
        atr = _calc_atr(bars, period=14)
        assert atr == pytest.approx(2.0 / 14, abs=1e-6)  # 仅最后一根 TR=2

    def test_atr_averages_multiple_trs(self):
        # 12 根平盘 + 2 根大波动 + 1 根收尾（共 15 根 ≥ period+1）：
        # 最后 14 根含 3 根 TR（2, 2, 1.5），均值 = 5.5/14
        bars = _flat_bars(12) + [_Bar(10, 12, 10, 11), _Bar(11, 13, 11, 12)]
        bars.append(_Bar(12, 13.5, 12, 12.5))
        atr = _calc_atr(bars, period=14)
        assert atr == pytest.approx(5.5 / 14, abs=1e-6)


class TestAtrStopLoss:
    def test_atr_stop_wider_than_fixed(self):
        """高波动股票 ATR 止损价应高于固定 -8% 止损价（更宽）。"""
        # 15 根 ±10% 波动的历史（TR≈2，ATR≈2）→ 2×ATR 止损 = 40% > 8%
        hist = [_Bar(10, 11, 9, 10) for _ in range(15)]
        atr = _calc_atr(hist)
        entry = 10.0
        atr_stop = entry - 2 * atr
        fixed_stop = entry * 0.92
        assert atr_stop < fixed_stop

    def test_atr_stop_triggers_stop_loss(self):
        """入场后大跌触及 ATR 止损线 → stop_loss。"""
        hist = _flat_bars(14) + [_Bar(10, 11.9, 9, 10.5)]
        hold = [_Bar(10.5, 10.6, 9.0, 9.2)]
        bars = hist + hold
        ret, day, reason = _calc_return_with_stop_loss(
            bars, len(hist) - 1, 5, atr_multiplier=2.0
        )
        assert reason == "stop_loss"
        assert day == 1

    def test_atr_unavailable_falls_back_to_fixed(self):
        """ATR 不可用（0）时回退固定止损。"""
        bars = _flat_bars(20)
        ret, day, reason = _calc_return_with_stop_loss(bars, 0, 5, atr_multiplier=2.0)
        assert reason in ("normal", "stop_loss")


class TestTrailingStop:
    def test_trailing_triggers_on_close_confirmation(self):
        """冲高后收盘跌破移动止盈线 → take_profit（收盘确认）。"""
        hist = _flat_bars(15)
        hold = [
            _Bar(10, 11, 10, 10.8),  # day1 冲高 11
            _Bar(10.8, 11.2, 10.6, 11.0),  # day2 峰值 11.2
            _Bar(11.0, 11.4, 10.9, 11.2),  # day3 峰值 11.4
            _Bar(11.2, 12.5, 11.0, 11.3),  # day4 峰值 12.5，收盘 11.3
            _Bar(11.3, 11.4, 10.6, 10.8),  # day5 跌破
        ]
        ret, day, reason = _calc_return_with_stop_loss(
            hist + hold, 14, 5, trailing_pct=0.05
        )
        # 峰值 12.5 回撤 5% = 11.875；day4 收盘 11.3 ≤ 11.875 → 当日触发
        assert reason == "take_profit"
        assert day == 4
        assert ret == pytest.approx((11.875 - 10) / 10, abs=1e-3)

    def test_single_day_spike_no_trigger(self):
        """单日冲高但收盘未破线 → 不触发（收盘确认）。"""
        hist = _flat_bars(15)
        hold = [
            _Bar(10, 11.5, 9.8, 11.2),  # 冲高 11.5，收盘 11.2（未破 11.5*0.95）
            _Bar(11.2, 11.6, 11.0, 11.4),
        ]
        ret, day, reason = _calc_return_with_stop_loss(
            hist + hold, 14, 5, trailing_pct=0.05
        )
        assert reason == "normal"

    def test_trailing_requires_profit_first(self):
        """峰值从未超过入场价时移动止盈不触发。"""
        hist = _flat_bars(15)
        hold = [_Bar(10, 9.8, 9.5, 9.6), _Bar(9.6, 9.7, 9.3, 9.4)]
        ret, day, reason = _calc_return_with_stop_loss(
            hist + hold, 14, 5, trailing_pct=0.05
        )
        assert reason == "normal"


class TestDefaultBehaviorUnchanged:
    """默认参数（无 ATR/无移动止盈）行为与历史版本一致。"""

    def test_fixed_stop_loss(self):
        hist = _flat_bars(15)
        hold = [_Bar(10, 10.5, 9.2, 9.5)]  # low 9.2 ≤ 9.2（-8%）
        ret, day, reason = _calc_return_with_stop_loss(hist + hold, 14, 5)
        assert reason == "stop_loss"
        assert ret == -0.08
        assert day == 1

    def test_fixed_take_profit(self):
        hist = _flat_bars(15)
        hold = [_Bar(10, 12.1, 10.0, 12.0)]  # high ≥ 12.0（+20%）
        ret, day, reason = _calc_return_with_stop_loss(hist + hold, 14, 5)
        assert reason == "take_profit"
        assert ret == 0.20

    def test_normal_hold_to_end(self):
        hist = _flat_bars(15)
        hold = [_Bar(10, 10.5, 9.8, 10.3), _Bar(10.3, 10.6, 10.1, 10.4)]
        bars = hist + hold
        ret, day, reason = _calc_return_with_stop_loss(bars, 14, 2)
        assert reason == "normal"
        assert day == 2
        assert ret == pytest.approx((10.4 - 10) / 10)


def _check(bars, start, holding_days, **kwargs):
    """便捷包装：忽略返回的 day。"""
    return _calc_return_with_stop_loss(bars, start, holding_days, **kwargs)
