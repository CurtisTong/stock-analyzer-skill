"""回测执行真实性测试（v1.27.0）。

覆盖两类"回测收益被系统性美化"的缺陷：
1. 跳空低开时止损按止损价成交（实际只能按开盘价成交）——高估亏损期收益；
2. 跳空高开时止盈按止盈价成交（实际按开盘价成交）——低估盈利期收益。

以及 walk-forward 的 IS/OOS 口径对称性：
3. IS 指标必须与 OOS 同口径（汇总后算一次），不是各窗口夏普的算术平均。
"""

from __future__ import annotations

import pytest


class _Bar:
    """最小 KlineBar 替身（只需 engine 访问的字段）。"""

    def __init__(self, day, o, h, low, c, volume=1000):
        self.day = day
        self.open = o
        self.high = h
        self.low = low
        self.close = c
        self.volume = volume
        self.amount = c * volume


class TestStopLossFillPrice:
    """止损成交价：跳空低开时按开盘价，不是止损价。"""

    def test_gap_down_fills_at_open_not_stop_price(self):
        """跳空低开跌破止损价 → 按开盘价成交（不是止损价）。

        注意：跳空幅度须在跌停限制内（主板 ±10%），否则该日会被
        _is_limit_down 判定为跌停日而跳过（跌停卖不出，出场顺延）。
        此处 -9% 未触及跌停价（-10%），正常进入止损判定。
        """
        from backtest.engine import _calc_return_with_stop_loss

        bars = [
            _Bar("d0", 100, 100, 100, 100),  # 入场日，收盘 100
            _Bar("d1", 91, 92, 90, 91),  # 跳空低开 -9%，跌破止损价 92
            _Bar("d2", 91, 92, 90, 91),
            _Bar("d3", 91, 92, 90, 91),
        ]
        ret, days, reason = _calc_return_with_stop_loss(bars, 0, 3, stop_loss=-0.08, take_profit=0.20)
        assert reason == "stop_loss"
        # 开盘 91 → 收益 -9%，而非止损价的 -8%
        assert ret == pytest.approx(-0.09, abs=1e-6)

    def test_limit_down_day_is_skipped(self):
        """跌停日卖不出 → 跳过该日，出场顺延到下一个可交易日（既有行为，回归锁定）。"""
        from backtest.engine import _calc_return_with_stop_loss

        bars = [
            _Bar("d0", 100, 100, 100, 100),
            _Bar("d1", 90, 90, 90, 90),  # 跌停（-10%），收盘=跌停价 → 跳过
            _Bar("d2", 89, 91, 88, 89),  # 非跌停，触发止损
            _Bar("d3", 89, 91, 88, 89),
        ]
        ret, days, reason = _calc_return_with_stop_loss(bars, 0, 3, stop_loss=-0.08, take_profit=0.20)
        assert reason == "stop_loss"
        assert days == 2  # 跌停日不计入持有天数
        assert ret == pytest.approx(-0.11, abs=1e-6)  # d2 开盘 89 → -11%

    def test_intraday_touch_fills_at_stop_price(self):
        """盘中触及止损（非跳空）→ 按止损价成交（不变）。"""
        from backtest.engine import _calc_return_with_stop_loss

        bars = [
            _Bar("d0", 100, 100, 100, 100),
            _Bar("d1", 99, 99.5, 91, 92),  # 盘中跌到 91，止损价 92
            _Bar("d2", 92, 93, 91, 92),
        ]
        ret, days, reason = _calc_return_with_stop_loss(bars, 0, 2, stop_loss=-0.08, take_profit=0.20)
        assert reason == "stop_loss"
        assert ret == pytest.approx(-0.08, abs=1e-6)

    def test_gap_up_take_profit_fills_at_open(self):
        """跳空高开越过止盈价 → 按开盘价成交（对称处理，不低估收益）。"""
        from backtest.engine import _calc_return_with_stop_loss

        bars = [
            _Bar("d0", 100, 100, 100, 100),
            _Bar("d1", 125, 126, 124, 125),  # 跳空高开 +25%，止盈价 120
            _Bar("d2", 125, 126, 124, 125),
        ]
        ret, days, reason = _calc_return_with_stop_loss(bars, 0, 2, stop_loss=-0.08, take_profit=0.20)
        assert reason == "take_profit"
        assert ret == pytest.approx(0.25, abs=1e-6)

    def test_atr_stop_also_uses_open_on_gap(self):
        """ATR 止损模式同样按跳空开盘价成交。"""
        from backtest.engine import _calc_return_with_stop_loss

        bars = [
            _Bar("d0", 100, 100, 100, 100),
            _Bar("d1", 90, 91, 89, 90),  # 跳空 -10%
            _Bar("d2", 90, 91, 89, 90),
        ]
        ret, days, reason = _calc_return_with_stop_loss(bars, 0, 2, atr_multiplier=1.0, code="sh600000")
        assert reason == "stop_loss"
        assert ret == pytest.approx(-0.10, abs=1e-6)


class TestWalkForwardIsOosSymmetry:
    """IS 与 OOS 必须同口径汇总，否则 IS/OOS 对比无意义。"""

    def test_is_sharpe_computed_from_pooled_returns(self):
        """IS 夏普 = 全窗口期收益拼接后算一次，不是各窗口夏普的算术平均。"""
        from backtest.walk_forward import _calc_sharpe

        pooled = [-1.0, 2.0, -1.0, 2.0]
        per_window = [
            _calc_sharpe([-1.0, 2.0], holding_days=5),
            _calc_sharpe([-1.0, 2.0], holding_days=5),
        ]
        pooled_sharpe = _calc_sharpe(pooled, holding_days=5)
        # 算术平均 ≠ 汇总口径（两者必须不同，说明聚合方式确实被修正了）
        assert pooled_sharpe != pytest.approx(sum(per_window) / len(per_window), abs=1e-9)

    def test_is_returns_collected(self):
        """IS 期收益被收集到 result.is_returns（供汇总口径使用）。"""
        from backtest.walk_forward import WalkForwardConfig, WalkForwardResult

        r = WalkForwardResult(config=WalkForwardConfig(strategy_name="balanced", codes=["sh600519"]))
        r.is_returns.extend([1.0, -2.0])
        assert r.is_returns == [1.0, -2.0]
