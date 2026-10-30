"""组合保护机制三件套测试（v1.24.0）。"""

from __future__ import annotations

import pytest

from portfolio.guardrails import (
    check_consecutive_losses,
    check_cooldown,
    check_max_drawdown,
    check_protections,
)


def _trade(code, profit, pct, sell_date):
    return {"code": code, "profit": profit, "profit_pct": pct, "sell_date": sell_date}


class TestMaxDrawdown:
    def test_deep_drawdown_triggers(self):
        r = check_max_drawdown([100, 120, 110, 90], threshold_pct=15.0)
        assert r["triggered"] is True
        # 峰 120 → 谷 90：回撤 25%
        assert r["drawdown_pct"] == pytest.approx(25.0)

    def test_shallow_drawdown_no_trigger(self):
        r = check_max_drawdown([100, 110, 105], threshold_pct=15.0)
        assert r["triggered"] is False
        assert r["drawdown_pct"] == pytest.approx(4.55, abs=0.01)

    def test_short_series_returns_none(self):
        assert check_max_drawdown([100]) is None


class TestConsecutiveLosses:
    def test_three_streak_triggers(self):
        trades = [
            _trade("A", 100, 5.0, "2026-10-01"),
            _trade("B", -50, -3.0, "2026-10-05"),
            _trade("C", -80, -4.0, "2026-10-10"),
            _trade("D", -120, -6.0, "2026-10-15"),
        ]
        r = check_consecutive_losses(trades, n=3)
        assert r["triggered"] is True
        assert r["consecutive_losses"] == 3

    def test_streak_broken_by_win(self):
        trades = [
            _trade("B", -50, -3.0, "2026-10-05"),
            _trade("C", 100, 5.0, "2026-10-10"),
            _trade("D", -120, -6.0, "2026-10-15"),
        ]
        r = check_consecutive_losses(trades, n=3)
        assert r["triggered"] is False
        assert r["consecutive_losses"] == 1

    def test_empty_returns_none(self):
        assert check_consecutive_losses([]) is None


class TestCooldown:
    def test_within_cooldown_triggers(self):
        trades = [_trade("sh600519", 100, 5.0, "2026-10-10")]
        r = check_cooldown(trades, "sh600519", cooldown_days=10, today="2026-10-15")
        assert r["triggered"] is True
        assert r["days_left"] == 5

    def test_past_cooldown_clear(self):
        trades = [_trade("sh600519", 100, 5.0, "2026-10-10")]
        r = check_cooldown(trades, "sh600519", cooldown_days=10, today="2026-10-25")
        assert r["triggered"] is False

    def test_irrelevant_code_returns_none(self):
        trades = [_trade("sh600519", 100, 5.0, "2026-10-10")]
        assert check_cooldown(trades, "sz000001", today="2026-10-15") is None


class TestCheckProtections:
    def test_all_clear(self):
        trades = [
            _trade("A", 100, 5.0, "2026-10-01"),
            _trade("B", 50, 2.0, "2026-10-05"),
        ]
        r = check_protections(trades)
        assert r["all_clear"] is True
        assert "全部正常" in r["summary"]

    def test_drawdown_and_losses_trigger(self):
        trades = [
            _trade("A", 100, 5.0, "2026-09-01"),
            _trade("B", -150, -8.0, "2026-10-01"),
            _trade("C", -120, -6.0, "2026-10-10"),
            _trade("D", -180, -9.0, "2026-10-15"),
        ]
        r = check_protections(trades)
        assert r["all_clear"] is False
        assert (
            "drawdown" in [k for k, v in r.items() if isinstance(v, dict) and v.get("triggered")]
            or r["losses"]["triggered"]
        )
        assert "保护触发" in r["summary"]

    def test_cooldown_included(self):
        trades = [_trade("sh600519", 100, 5.0, "2026-10-26")]
        r = check_protections(trades, cooldown_codes=["sh600519"])
        assert "sh600519" in r["cooldowns"]
        assert r["all_clear"] is False


class TestTradeOrderIndependence:
    """TradeLog.query() 返回降序（最新在前），本模块不得依赖调用方顺序。"""

    def _trades(self):
        return [
            _trade("A", 100, 5.0, "2026-10-01"),
            _trade("B", -50, -3.0, "2026-10-05"),
            _trade("C", -80, -4.0, "2026-10-10"),
            _trade("D", -120, -6.0, "2026-10-15"),
        ]

    def test_consecutive_losses_same_for_both_orders(self):
        """升序与降序输入必须给出相同的连亏计数（修复前 3 vs 0）。"""
        asc = self._trades()
        desc = list(reversed(asc))
        assert check_consecutive_losses(asc, n=3)["consecutive_losses"] == (
            check_consecutive_losses(desc, n=3)["consecutive_losses"]
        )
        assert check_consecutive_losses(asc, n=3)["consecutive_losses"] == 3
        assert check_consecutive_losses(desc, n=3)["triggered"] is True

    def test_cooldown_uses_most_recent_sale(self):
        """同票多笔清仓时取最近一笔（修复前降序输入会取到最老的一笔）。"""
        trades = [
            _trade("sh600519", 100, 5.0, "2026-10-01"),
            _trade("sh600519", 100, 5.0, "2026-10-20"),
        ]
        r = check_cooldown(trades, "sh600519", cooldown_days=10, today="2026-10-25")
        assert r["triggered"] is True
        assert r["days_left"] == 5  # 10-20 → 10-25 = 5 天
        assert "2026-10-20" in r["message"]


class TestDrawdownOnEquityBasis:
    """回撤熔断必须按账户权益口径，亏损账户不得恒为 0。"""

    def test_deep_loss_account_triggers_with_initial_capital(self):
        trades = [
            _trade("A", -100, -10.0, "2026-10-01"),
            _trade("B", -200, -20.0, "2026-10-05"),
            _trade("C", -300, -30.0, "2026-10-10"),
        ]
        r = check_protections(trades, initial_capital=1000.0)
        dd = r["drawdown"]
        assert dd is not None
        # 权益 1000 → 900 → 700 → 400：峰值 900，谷值 400 → 回撤 55.56%
        assert dd["drawdown_pct"] == pytest.approx(55.56, abs=0.01)
        assert dd["triggered"] is True

    def test_loss_account_without_capital_still_detects_drawdown(self):
        """无初始资金时退化为利润口径，但负值序列仍不得恒为 0 回撤。"""
        r = check_max_drawdown([-100.0, -200.0, -300.0])
        assert r["drawdown_pct"] > 0.0

    def test_equity_scale_prevents_false_alarm(self):
        """资本 100 万时，利润从 +1000 掉到 +800 的微额回撤不应被算成 20%。"""
        r = check_max_drawdown([1_001_000.0, 1_000_800.0])
        assert r["drawdown_pct"] == pytest.approx(0.02, abs=0.01)
        assert r["triggered"] is False
