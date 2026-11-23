"""执行口径断层修复单测（hermetic：monkeypatch 报价/K线，不连网、不读真实持仓取数）。

操盘/Chief 2026-11-23 定案：唯一权威源是 holdings_levels.json，portfolio.json 只当历史。
snapshot() 改读 LEVELS（第1/2条）、仓位估算与权威分开（第3条）、闸门2b降级为WARN（第4条）。

共享脚本在仓库外 stock-team/monitor/，用 importlib 按路径加载。
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path

import pytest

_MONITOR = Path(__file__).resolve().parents[3] / "monitor"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, _MONITOR / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mh():
    return _load("monitor_holdings_under_test", "monitor_holdings.py")


@pytest.fixture(scope="module")
def dc():
    return _load("daily_card_under_test", "daily_card.py")


@pytest.fixture(scope="module")
def ch():
    return _load("check_holdings_under_test", "check_holdings.py")


def _isolate(mh, monkeypatch):
    def fake_quote(code):
        return {"price": 2.5, "change_pct": 1.0, "open": 2.5, "prev_close": 2.475}

    monkeypatch.setattr(mh, "quote", fake_quote)
    monkeypatch.setattr(mh, "kline_last_day", lambda *a, **k: "2026-11-23")


class TestSnapshotReadsLevels:
    def test_position_split_estimate_vs_book(self, mh, monkeypatch):
        _isolate(mh, monkeypatch)
        s = mh.snapshot("盘前")
        # 估算仓位（实时市值/实时总资产）与账本权威仓位分开
        assert s["position_pct"] is not None
        assert s["position_pct_book"] == pytest.approx(72.2, abs=0.05)  # LEVELS combined
        assert s["book_price_date"] == "2026-11-23"
        assert "price_date_source" in s

    def test_holdings_from_levels_not_portfolio(self, mh, monkeypatch):
        _isolate(mh, monkeypatch)
        s = mh.snapshot("盘前")
        codes = {r["code"] for r in s["rows"]}
        # 应来自 LEVELS 的 9 只（含广合 sz001389），不含已清仓深100 sz159901
        assert "sz001389" in codes
        assert "sz159901" not in codes
        assert len(codes) == 9

    def test_no_portfolio_dependency(self, mh):
        # snapshot() 源码不再出现 PORTFOLIO 取数
        import inspect
        src = inspect.getsource(mh.snapshot)
        assert "PORTFOLIO.read_text" not in src


class TestCardShowsBothPositions:
    def test_card_labels_estimate_and_book(self, dc, mh, monkeypatch):
        _isolate(mh, monkeypatch)
        snap = mh.snapshot("盘前")
        gate = {"ok": True, "problems": [], "price_date": "2026-11-23"}
        card = dc.build("盘前", snap, gate)
        pos_line = [line for line in card.splitlines() if line.startswith("仓位")][0]
        assert "估算" in pos_line
        assert "账本权威" in pos_line
        assert "72.2%" in pos_line


class TestGatePortfolioDowngraded:
    def test_portfolio_drift_is_warn_not_fail(self, ch, tmp_path):
        """闸门2b：portfolio.json 漂移只 WARN，不让历史文件决定闸门红绿。"""
        ledger = {
            "_meta": {
                "updated": "2026-11-23T23:50:00", "price_date": "2026-11-23",
                "combined": {"total_assets": 1000.0, "market_value": 700.0, "cash": 300.0, "position_pct": 70.0},
                "accounts": {},
            },
            "sh600000": {"name": "A", "qty": 100, "cost_avg": 6.0, "px": 7.0, "pct_of_assets": 70.0},
        }
        # portfolio 给一个漂移价
        port = {"positions": [{"code": "sh600000", "px": 9.0}]}
        lp = tmp_path / "ledger.json"
        pp = tmp_path / "portfolio.json"
        lp.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
        pp.write_text(json.dumps(port, ensure_ascii=False), encoding="utf-8")
        out = ch.check(lp, now=datetime(2026, 11, 23, 23, 50), price_date="2026-11-23", portfolio_path=pp)
        # 漂移应 WARN，不 FAIL（账户字段缺失本就 FAIL，这里只看漂移项等级）
        drift = [p for p in out["problems"] if "历史文件漂移" in p["item"]]
        assert drift and all(p["level"] == "WARN" for p in drift)
