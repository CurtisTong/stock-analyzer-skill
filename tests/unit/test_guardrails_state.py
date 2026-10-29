"""保护机制状态持久化 + 硬阻止测试（v1.25 复审修复）。

背景：guardrails 原是纯函数——熔断"是否处于熔断中"完全依赖当前交易内容，
追加一笔盈利交易连亏计数归零即自动解除熔断，没有任何冷却锁定；进程重启后
状态全丢。这与"熔断"的语义不符——熔断应当在冷却期内持续生效。
"""

from __future__ import annotations

import pytest


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    """把状态文件指向临时目录（避免污染真实数据）。"""
    from portfolio import guardrails

    path = tmp_path / "guardrails_state.json"
    monkeypatch.setattr(guardrails, "_state_path", lambda: path)
    return path


class TestBreakerState:
    def test_record_and_load(self, state_file):
        from portfolio.guardrails import clear_breakers, load_state, record_breaker

        clear_breakers()
        entry = record_breaker("losses", "连续 3 笔亏损")
        assert entry["kind"] == "losses"
        assert entry["until"]
        state = load_state()
        assert len(state["breakers"]) == 1
        assert state["breakers"][0]["message"] == "连续 3 笔亏损"

    def test_survives_restart(self, state_file):
        """状态必须跨进程/重启保留。"""
        from portfolio.guardrails import clear_breakers, load_state, record_breaker

        clear_breakers()
        record_breaker("drawdown", "回撤超限")
        # 模拟重启：重新读文件
        assert load_state()["breakers"][0]["message"] == "回撤超限"

    def test_expired_breaker_inactive(self, state_file):
        """冷却期过期的熔断不再生效，并被自动清理。"""
        from portfolio.guardrails import _active_breakers, clear_breakers, load_state, record_breaker

        clear_breakers()
        record_breaker("losses", "旧熔断")
        # 把到期日改到过去
        state = load_state()
        state["breakers"][0]["until"] = "2020-01-01"
        from portfolio.guardrails import save_state

        save_state(state)

        assert _active_breakers(load_state()) == []
        assert load_state()["breakers"] == []

    def test_clear_by_kind(self, state_file):
        from portfolio.guardrails import clear_breakers, load_state, record_breaker

        clear_breakers()
        record_breaker("losses", "a")
        record_breaker("drawdown", "b")
        assert clear_breakers("losses") == 1
        assert len(load_state()["breakers"]) == 1
        assert clear_breakers() == 1
        assert load_state()["breakers"] == []


class TestTradingAllowed:
    def test_blocked_when_breaker_active(self, state_file):
        """熔断生效时禁止加仓（硬阻止）。"""
        from portfolio.guardrails import clear_breakers, is_trading_allowed, record_breaker

        clear_breakers()
        allowed, reason = is_trading_allowed("sh600519")
        assert allowed is True

        record_breaker("losses", "连续亏损熔断")
        allowed, reason = is_trading_allowed("sh600519")
        assert allowed is False
        assert "连续亏损熔断" in reason

    def test_allowed_after_clear(self, state_file):
        from portfolio.guardrails import clear_breakers, is_trading_allowed, record_breaker

        clear_breakers()
        record_breaker("losses", "x")
        assert is_trading_allowed("sh600519")[0] is False
        clear_breakers()
        assert is_trading_allowed("sh600519")[0] is True


class TestBreakerSurvivesWinningTrade:
    def test_breaker_not_cleared_by_profit(self, state_file):
        """追加一笔盈利交易不得自动解除熔断。

        熔断状态的写入是显式的（sync_breakers），检查本身是纯读——
        因此这里要先同步一次熔断状态，再验证盈利交易不会解除它。
        """
        from portfolio.guardrails import check_protections, clear_breakers, load_state, sync_breakers

        clear_breakers()
        losing = [
            {"code": "A", "profit": -100, "profit_pct": -10.0, "sell_date": "2026-10-01"},
            {"code": "B", "profit": -200, "profit_pct": -20.0, "sell_date": "2026-10-05"},
            {"code": "C", "profit": -300, "profit_pct": -30.0, "sell_date": "2026-10-10"},
        ]
        r1 = check_protections(losing)
        assert r1["losses"]["triggered"] is True

        # 显式同步：熔断落盘
        sync_breakers(losing)
        assert len(load_state()["breakers"]) >= 1

        # 追加一笔盈利交易：连亏计数归零，但已落盘的熔断仍在
        winning = losing + [{"code": "D", "profit": 500, "profit_pct": 8.0, "sell_date": "2026-10-20"}]
        r2 = check_protections(winning)
        assert r2["losses"]["triggered"] is False  # 连亏计数归零
        # 但熔断仍生效（active_breakers 非空）
        assert r2.get("active_breakers")
        assert r2["all_clear"] is False

    def test_check_protections_has_no_write_side_effect(self):
        """检查函数不得写状态文件（否则检查不可重入、会污染数据）。"""
        from portfolio.guardrails import check_protections, load_state

        losing = [
            {"code": "A", "profit": -100, "profit_pct": -10.0, "sell_date": "2026-10-01"},
            {"code": "B", "profit": -200, "profit_pct": -20.0, "sell_date": "2026-10-05"},
            {"code": "C", "profit": -300, "profit_pct": -30.0, "sell_date": "2026-10-10"},
        ]
        before = load_state()["breakers"]
        check_protections(losing)
        assert load_state()["breakers"] == before


class TestSyncBreakers:
    def test_sync_writes_breaker(self, state_file):
        from portfolio.guardrails import clear_breakers, load_state, sync_breakers

        clear_breakers()
        losing = [
            {"code": "A", "profit": -100, "profit_pct": -10.0, "sell_date": "2026-10-01"},
            {"code": "B", "profit": -200, "profit_pct": -20.0, "sell_date": "2026-10-05"},
            {"code": "C", "profit": -300, "profit_pct": -30.0, "sell_date": "2026-10-10"},
        ]
        active = sync_breakers(losing)
        assert active
        assert load_state()["breakers"]
