"""Code Review 2026-11-21（3.4 / 4.4）修复的可失败回归测试。

覆盖条目：P1-25 / P1-26 / P1-27 / P2(回撤口径 / update_watch / force /
锁 TOCTOU / price=0 / 相关系数对齐) / P3(限流 / fsync)。
测试命名带 review 条目号，便于以后定位被回归破坏的不变量。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import portfolio.web.app as web_app
import portfolio.web.utils as web_utils
from portfolio.crud import remove_position
from portfolio.guardrails import clear_breakers, is_trading_allowed, load_state, record_breaker
from portfolio.manager import PortfolioManager
from portfolio.web.dispatch import dispatch


def _make_manager(tmp_path: Path, positions=None, watchlist=None, total_assets=None) -> PortfolioManager:
    data = {"version": 2, "positions": positions or [], "watchlist": watchlist or []}
    if total_assets is not None:
        data["total_assets"] = total_assets
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return PortfolioManager(str(path))


def _start_server(tmp_path: Path, monkeypatch):
    """临时端口启动 Web 服务（token / 数据文件均隔离）。"""
    monkeypatch.setattr(web_utils, "_TOKEN_DIR", tmp_path)
    monkeypatch.setattr(web_utils, "_TOKEN_FILE", tmp_path / "portfolio_web.token")
    monkeypatch.setattr(web_utils, "_token", None)
    data_file = tmp_path / "portfolio.json"
    data_file.write_text('{"version":2,"positions":[],"watchlist":[]}', encoding="utf-8")
    server = web_app.make_server("127.0.0.1", 0, data_file=str(data_file))
    port = server.server_address[1]
    web_app._rebuild_allowed_origins("127.0.0.1", port)
    web_app.Handler.reset_rate_limit_for_tests()
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, port, data_file, web_utils._ensure_token()


def _request(
    port: int,
    method: str,
    token: str | None,
    body: bytes = b"",
    origin: str | None = None,
) -> tuple[int, str]:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if origin is not None:
        headers["Origin"] = origin
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/positions",
        data=body if method == "POST" else None,
        method=method,
        headers=headers,
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


# ═══════════════════════════════════════════════════════════════
# P1-25 清仓不喂熔断
# ═══════════════════════════════════════════════════════════════


class TestP125ClearFeedsBreakers:
    def test_three_losing_clear_positions_trigger_breaker(self, tmp_path):
        """连续 3 笔亏损清仓 → 连亏熔断落盘并硬阻止加仓。"""
        from portfolio.trade_log import TradeLog

        clear_breakers()
        positions = [
            {"code": f"sh60000{i}", "name": f"测试{i}", "cost": 100.0, "quantity": 100, "tags": []}
            for i in range(1, 4)
        ]
        pm = _make_manager(tmp_path, positions, total_assets=100_000)

        for i, pos in enumerate(positions, start=1):
            assert remove_position(pm, pos["code"], sell_price=90.0 - i) is True

        trades = TradeLog().query()
        assert len(trades) == 3
        assert all(t["profit"] < 0 and t["profit_pct"] < 0 for t in trades)
        assert all(t["sell_price_source"] == "provided" for t in trades)
        # 核心不变量：熔断状态已写入且生效
        assert any(b["kind"] == "losses" for b in load_state()["breakers"])
        assert is_trading_allowed("sh600001")[0] is False

    def test_sell_price_fallback_annotates_source(self, tmp_path, monkeypatch):
        """无显式卖价：按现价估算标注 current_quote；再无行情按成本估算。"""
        from portfolio.trade_log import TradeLog

        class _Quote:
            def __init__(self, price):
                self.price = price

        monkeypatch.setattr("data.get_quotes", lambda codes, use_cache=True: [_Quote(80.0)])
        pm = _make_manager(
            tmp_path,
            [{"code": "sh600010", "name": "A", "cost": 100.0, "quantity": 10, "tags": []}],
        )
        remove_position(pm, "sh600010")
        trade = TradeLog().query()[0]
        assert trade["sell_price"] == 80.0
        assert trade["sell_price_source"] == "current_quote"
        assert trade["profit"] < 0

        monkeypatch.setattr("data.get_quotes", lambda codes, use_cache=True: [])
        pm = _make_manager(
            tmp_path,
            [{"code": "sh600011", "name": "B", "cost": 100.0, "quantity": 10, "tags": []}],
        )
        remove_position(pm, "sh600011")
        trade = TradeLog().query(code="sh600011")[0]
        assert trade["sell_price_source"] == "cost_estimate"
        assert trade["profit"] == 0.0  # 成本估算不得伪造盈亏

    def test_sync_breakers_uses_absolute_profit(self):
        """profit_pct 缺失（旧记录）但绝对 profit 为负时仍判连亏。"""
        from portfolio.guardrails import check_consecutive_losses

        trades = [
            {"code": "A", "profit": -100, "sell_date": "2026-10-01"},
            {"code": "B", "profit": -200, "sell_date": "2026-10-02"},
            {"code": "C", "profit": -300, "sell_date": "2026-10-03"},
        ]
        result = check_consecutive_losses(trades, n=3)
        assert result["triggered"] is True
        assert result["consecutive_losses"] == 3

    def test_dispatch_remove_position_passes_sell_price(self, tmp_path):
        """Web 清仓入口采集卖价并透传。"""
        from portfolio.trade_log import TradeLog

        pm = _make_manager(
            tmp_path,
            [{"code": "sh600020", "name": "C", "cost": 100.0, "quantity": 10, "tags": []}],
        )
        result = dispatch(pm, {"action": "remove_position", "code": "sh600020", "sell_price": 88.0})
        assert result["ok"] is True
        assert TradeLog().query()[0]["profit"] < 0


# ═══════════════════════════════════════════════════════════════
# P1-26 NaN / Infinity 绕过校验
# ═══════════════════════════════════════════════════════════════


class TestP126RejectNonFinite:
    def test_parse_float_rejects_nan_infinity(self):
        from portfolio.web.utils import _parse_float

        assert _parse_float(float("nan")) is None
        assert _parse_float("NaN") is None
        assert _parse_float(float("inf")) is None
        assert _parse_float("-Infinity") is None
        assert _parse_float(True) is None
        assert _parse_float(12.5) == 12.5

    def test_loads_json_rejects_non_finite_constants(self):
        from portfolio.web.utils import loads_json

        for raw in ('{"cost": NaN}', '{"cost": Infinity}', '{"cost": -Infinity}'):
            with pytest.raises(ValueError):
                loads_json(raw)

    @pytest.mark.parametrize("raw", [b'{"action":"add_position","code":"sh600989","cost":NaN,"quantity":100}',
                                     b'{"action":"add_position","code":"sh600989","cost":Infinity,"quantity":100}'])
    def test_post_nan_returns_400_and_does_not_write(self, tmp_path, monkeypatch, raw):
        """POST NaN/Infinity → 400 且 portfolio.json 未被改写。"""
        server, port, data_file, token = _start_server(tmp_path, monkeypatch)
        try:
            before = data_file.read_text(encoding="utf-8")
            status, _ = _request(port, "POST", token, raw)
            assert status == 400
            assert data_file.read_text(encoding="utf-8") == before
        finally:
            server.shutdown()
            server.server_close()

    def test_nan_string_cost_rejected_by_dispatch(self, tmp_path):
        pm = _make_manager(tmp_path)
        result = dispatch(pm, {"action": "add_position", "code": "sh600989", "cost": "nan", "quantity": 100})
        assert result["ok"] is False and result["code"] == 400
        assert pm.get_positions() == []


# ═══════════════════════════════════════════════════════════════
# P1-27 破位报告渲染崩溃
# ═══════════════════════════════════════════════════════════════


class TestP127BreakdownMarkdownNoQuote:
    def test_technical_breakdown_without_quote_renders(self, tmp_path):
        """技术破位 + 无行情 → pnl_pct=None，Markdown 正常生成。"""
        pm = _make_manager(
            tmp_path,
            [{"code": "sh600030", "name": "中信证券", "cost": 20.0, "quantity": 100, "tags": []}],
        )
        report = pm.health_report(
            quotes={},
            technical_features={"sh600030": {"breakdown": True, "breakdown_reason": "support_break"}},
            auto_technical=False,
        )
        assert report["breakdown_positions"]
        assert report["breakdown_positions"][0]["pnl_pct"] is None
        md = pm.health_report_markdown(report)
        assert "已破位标的" in md
        assert "N/A" in md


# ═══════════════════════════════════════════════════════════════
# P2 回撤口径 / price=0 / update_watch / force
# ═══════════════════════════════════════════════════════════════


class TestP2DrawdownCapitalBasis:
    @pytest.fixture
    def trades(self, tmp_path):
        from portfolio.trade_log import TradeLog

        tl = TradeLog()
        for i in range(3):
            tl.record(code=f"sh6000{i + 1}0", name="测试", cost=100.0, quantity=100, sell_price=90.0)
        return tl.query()

    @pytest.mark.usefixtures("trades")
    def test_uses_total_assets_when_present(self, tmp_path):
        pm = _make_manager(
            tmp_path,
            [{"code": "sh600099", "name": "持仓", "cost": 100.0, "quantity": 100, "tags": []}],
            total_assets=1_000_000,
        )
        report = pm.health_report(
            quotes={"sh600099": {"price": 100.0, "change_pct": 0.0}},
            technical_features={},
            auto_technical=False,
        )
        assert report["protections"]["capital_basis"] == "total_assets"
        assert not any("回撤口径降级" in w for w in report["warnings"])
        # 100 万资产上亏 3000 元 ≈ 0.3%，不应触发 15% 回撤
        assert report["protections"]["drawdown"]["triggered"] is False

    @pytest.mark.usefixtures("trades")
    def test_missing_total_assets_marked_degraded(self, tmp_path):
        pm = _make_manager(
            tmp_path,
            [{"code": "sh600099", "name": "持仓", "cost": 100.0, "quantity": 100, "tags": []}],
        )
        report = pm.health_report(
            quotes={"sh600099": {"price": 100.0, "change_pct": 0.0}},
            technical_features={},
            auto_technical=False,
        )
        assert report["protections"]["capital_basis"] == "missing"
        assert any("回撤口径降级" in w for w in report["warnings"])


class TestP2ZeroPriceIsMissingQuote:
    def test_zero_price_does_not_fake_loss(self, tmp_path):
        pm = _make_manager(
            tmp_path,
            [{"code": "sh600989", "name": "宝丰能源", "cost": 22.37, "quantity": 4000, "tags": []}],
        )
        report = pm.health_report(
            quotes={"sh600989": {"price": 0, "change_pct": 0}},
            technical_features={},
            auto_technical=False,
        )
        assert report["totals"]["pnl"] is None
        assert report["totals"]["pnl_pct"] is None
        assert report["positions"][0]["pnl"] is None
        assert report["positions"][0]["pnl_pct"] is None
        assert "行情缺失" in report["risk_rating"]


class TestP2UpdateWatchStrictParsing:
    def test_invalid_string_returns_400_without_clearing(self, tmp_path):
        watch = {
            "code": "sh600989",
            "name": "宝丰能源",
            "target_buy": 18.0,
            "target_sell": 25.0,
            "added_date": "2026-01-01",
        }
        pm = _make_manager(tmp_path, watchlist=[watch])
        result = dispatch(pm, {"action": "update_watch", "code": "sh600989", "target_buy": "abc"})
        assert result["ok"] is False and result["code"] == 400
        assert pm.get_watch("sh600989")["target_buy"] == 18.0

    def test_explicit_zero_clears_target(self, tmp_path):
        watch = {
            "code": "sh600989",
            "name": "宝丰能源",
            "target_buy": 18.0,
            "target_sell": 25.0,
            "added_date": "2026-01-01",
        }
        pm = _make_manager(tmp_path, watchlist=[watch])
        result = dispatch(
            pm,
            {"action": "update_watch", "code": "sh600989", "target_buy": 0, "target_sell": 0},
        )
        assert result["ok"] is True
        assert pm.get_watch("sh600989")["target_buy"] == 0
        assert pm.get_watch("sh600989")["target_sell"] == 0


class TestP2ForceEscapeHatch:
    def test_facade_force_overrides_breaker(self, tmp_path):
        clear_breakers()
        record_breaker("losses", "连亏熔断", cooldown_days=5)
        pm = _make_manager(tmp_path)
        with pytest.raises(ValueError, match="保护机制硬阻止"):
            pm.add_position("sh600989", "测试", 10.0, 100)
        assert pm.add_position("sh600989", "测试", 10.0, 100, force=True)["code"] == "sh600989"

    def test_dispatch_force_is_strict_boolean(self, tmp_path):
        clear_breakers()
        record_breaker("losses", "连亏熔断", cooldown_days=5)
        pm = _make_manager(tmp_path)
        body = {"action": "add_position", "code": "sh600989", "cost": 10.0, "quantity": 100}
        assert dispatch(pm, {**body, "force": "true"})["code"] == 400
        result = dispatch(pm, {**body, "force": True})
        assert result["ok"] is True
        assert "protection_force_override" in result["warn"]


# ═══════════════════════════════════════════════════════════════
# P2 锁 TOCTOU / P3 fsync
# ═══════════════════════════════════════════════════════════════


class TestP2FileLock:
    def test_old_timestamp_live_lock_not_stolen_and_no_unlink(self, tmp_path):
        """5 分钟前的活锁不得被误判 stale；锁文件不得被删了重建（TOCTOU）。"""
        from portfolio._file_utils import file_lock, lock_path

        path = tmp_path / "portfolio.json"
        lp = lock_path(path)
        lp.write_text(f"{os.getpid()}:{time.time() - 3600}", encoding="utf-8")
        inode_before = lp.stat().st_ino

        child = (
            "import fcntl,os,sys\n"
            "fd=os.open(sys.argv[1], os.O_RDWR)\n"
            "try:\n"
            "    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
            "    print('ACQUIRED')\n"
            "except BlockingIOError:\n"
            "    print('BLOCKED')\n"
            "finally:\n"
            "    os.close(fd)\n"
        )
        with file_lock(path, timeout=1):
            assert lp.exists()
            assert lp.stat().st_ino == inode_before
            out = subprocess.run(
                [sys.executable, "-c", child, str(lp)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert out.stdout.strip() == "BLOCKED", out.stderr
        assert lp.exists()  # 释放后保留锁文件，杜绝"删新锁"窗口

    def test_raw_write_fsync(self, tmp_path, monkeypatch):
        import portfolio._file_utils as fu

        real_fsync = os.fsync
        calls = []

        def _counted(fd):
            calls.append(fd)
            return real_fsync(fd)

        monkeypatch.setattr(fu.os, "fsync", _counted)
        fu.raw_write(tmp_path / "portfolio.json", {"version": 2})
        assert calls, "raw_write 必须 fsync 后再 os.replace"


# ═══════════════════════════════════════════════════════════════
# P2 相关系数按交易日对齐 / P3 限流
# ═══════════════════════════════════════════════════════════════


class TestP2CorrelationDateAlignment:
    @pytest.fixture
    def uneven_klines(self, monkeypatch):
        import portfolio_correlation as pc

        days = [f"2026-03-{d:02d}" for d in range(1, 31)]
        returns = {}
        for i, day in enumerate(days[1:]):
            returns[day] = 0.02 + i * 0.01 if i < 6 else 0.01 * ((i % 5) - 2)

        a_bars, b_bars = [], []
        price = 10.0
        for day in days:
            a_bars.append(type("_K", (), {"day": day, "close": price})())
            price *= 1 + returns.get(day, 0.0)
        price = 10.0
        for day in days:
            if day < days[6]:  # B 停牌，缺前 6 个交易日
                continue
            b_bars.append(type("_K", (), {"day": day, "close": price})())
            price *= 1 + returns.get(day, 0.0)

        def fake_kline(code, scale=240, datalen=60):
            return {"A": a_bars, "B": b_bars, "IDX": a_bars}.get(code, a_bars)

        monkeypatch.setattr(pc, "get_kline", fake_kline)
        return a_bars, b_bars

    @pytest.mark.usefixtures("uneven_klines")
    def test_matrix_aligns_by_day_not_head(self):
        from portfolio_correlation import compute_correlation_matrix

        result = compute_correlation_matrix(["A", "B"], index_code="IDX", window=30)
        assert result is not None
        # 按交易日对齐 → B 的收益序列是 A 的同日子集，相关性必须恰为 1；
        # 旧实现按头截断会得到约 -0.09。
        assert result["matrix"]["A"]["B"] == pytest.approx(1.0, abs=1e-6)

    @pytest.mark.usefixtures("uneven_klines")
    def test_stock_vs_portfolio_aligns_by_day(self):
        from portfolio_correlation import compute_stock_vs_portfolio

        result = compute_stock_vs_portfolio("A", ["B"], window=30)
        assert result is not None
        assert result["vs_portfolio_avg_corr"] == pytest.approx(1.0, abs=1e-6)

    def test_pearson_accepts_date_keyed_dicts(self):
        from portfolio_correlation import _pearson_corr

        a = {f"2026-01-{d:02d}": 0.01 * (i % 5 - 2) for i, d in enumerate(range(2, 16))}
        b = {key: value * 2 for key, value in reversed(list(a.items()))}
        assert _pearson_corr(a, b) == pytest.approx(1.0, abs=1e-6)


class TestP3RateLimitAfterAuth:
    def test_invalid_tokens_do_not_consume_valid_bucket(self, tmp_path, monkeypatch):
        server, port, _, token = _start_server(tmp_path, monkeypatch)
        monkeypatch.setattr(web_app, "_RATE_LIMIT_REQUESTS", 1)
        web_app.Handler.reset_rate_limit_for_tests()
        try:
            origin = f"http://127.0.0.1:{port}"
            for _ in range(3):
                # 带合法 Origin 走浏览器路径：修复前限流先于鉴权，
                # 这些无效 token 会按 IP 灌满窗口；修复后直接 401。
                status, _ = _request(port, "GET", "invalid-token", origin=origin)
                assert status == 401
            status, _ = _request(port, "GET", token, origin=origin)
            assert status == 200, "无效 token 不应灌满合法 token 的限流桶"
        finally:
            server.shutdown()
            server.server_close()
