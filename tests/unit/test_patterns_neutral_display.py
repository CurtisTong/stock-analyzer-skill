"""形态展示位分配 + 持仓盈亏并入回撤（v1.25 复审修复）。

背景：
- 中性形态（十字星）不产生买卖信号也不进 summary，却挤占展示位
  （实测 10 个位置里 7 个是十字星，真正的方向性形态只剩 3 个）。
- guardrails 的 position_pnl_pct 参数此前完全未使用——持仓浮亏时回撤看不到亏损。
"""

from __future__ import annotations

import pytest


def _mk(day, close, high=None, low=None, vol=1000, open_=None):
    high = high if high is not None else close
    low = low if low is not None else close
    return {
        "day": day,
        "open": close if open_ is None else open_,
        "close": close,
        "high": high,
        "low": low,
        "volume": vol,
    }


class TestDirectionalPatternsGetDisplaySlots:
    def test_neutral_patterns_do_not_squeeze_directional(self):
        """方向性形态优先占展示位。"""
        from strategies.patterns import PatternInput, detect_all_local_patterns

        # 8 根十字星（close == open）+ 1 根锤子线（长下影，方向性看涨）
        candles = [(10.0, 10.0, 10.1, 9.9)] * 8 + [(10.0, 9.8, 10.0, 9.0)]
        records = [_mk(f"2026-01-{i + 1:02d}", c, h, lo, open_=o) for i, (o, c, h, lo) in enumerate(candles)]
        closes = [r["close"] for r in records]
        inp = PatternInput(
            records=records,
            closes=closes,
            highs=[r["high"] for r in records],
            lows=[r["low"] for r in records],
            volumes=[1000] * len(closes),
            mas={},
            code="sh600519",
        )
        result = detect_all_local_patterns(inp)
        directional = [p for p in result["patterns"] if p["type"] in ("看涨", "看跌")]
        # 方向性形态必须在展示位里（不被中性形态挤掉）
        assert directional, result["patterns"]
        assert any(p["name"] == "锤子线" for p in directional), result["patterns"]
        # 展示位总数不超过上限
        assert len(result["patterns"]) <= 10

    def test_directional_patterns_not_squeezed_when_many_neutral(self):
        """方向性形态多于展示位时，全部方向性形态优先占位。"""
        from strategies.patterns import PatternInput, detect_all_local_patterns

        # 12 根十字星 + 3 根锤子线
        candles = [(10.0, 10.0, 10.1, 9.9)] * 12 + [(10.0, 9.8, 10.0, 9.0)] * 3
        records = [_mk(f"2026-03-{i + 1:02d}", c, h, lo, open_=o) for i, (o, c, h, lo) in enumerate(candles)]
        closes = [r["close"] for r in records]
        inp = PatternInput(
            records=records,
            closes=closes,
            highs=[r["high"] for r in records],
            lows=[r["low"] for r in records],
            volumes=[1000] * len(closes),
            mas={},
            code="sh600519",
        )
        result = detect_all_local_patterns(inp)
        directional = [p for p in result["patterns"] if p["type"] in ("看涨", "看跌")]
        # 3 个方向性形态全部保留，且不被十字星挤掉
        assert len(directional) == 3, result["patterns"]
        assert len(result["patterns"]) <= 10


class TestPositionPnlInDrawdown:
    def test_position_loss_counts_toward_drawdown(self):
        """持仓浮亏应计入回撤视角（此前 position_pnl_pct 参数完全未使用）。"""
        from portfolio.guardrails import check_protections

        # 两笔交易 → 权益序列至少 2 个点，回撤才可计算
        trades = [
            {"code": "A", "profit": 200, "profit_pct": 5.0, "sell_date": "2026-10-01"},
            {"code": "B", "profit": 100, "profit_pct": 2.0, "sell_date": "2026-10-05"},
        ]
        with_pnl = check_protections(trades, position_pnl_pct=-30.0, initial_capital=100000.0)
        without = check_protections(trades, initial_capital=100000.0)
        assert without["drawdown"] is not None
        # 浮亏 30% 应让回撤显著大于无浮亏时
        assert with_pnl["drawdown"]["drawdown_pct"] > without["drawdown"]["drawdown_pct"]
        assert with_pnl.get("position_pnl_pct") == -30.0

    def test_position_pnl_persisted_in_result(self):
        from portfolio.guardrails import check_protections

        trades = [{"code": "A", "profit": 100, "profit_pct": 5.0, "sell_date": "2026-10-01"}]
        r = check_protections(trades, position_pnl_pct=12.5)
        assert r["position_pnl_pct"] == 12.5
