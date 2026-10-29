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
