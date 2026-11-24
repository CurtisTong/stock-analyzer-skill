"""执行口径断层修复单测（hermetic：fixture 账本注入 + monkeypatch 报价/K线，不连网、不读本机真实持仓）。

操盘/Chief 2026-11-23 定案：唯一权威源是 holdings_levels.json，portfolio.json 只当历史。
snapshot() 改读 LEVELS（第1/2条）、仓位估算与权威分开（第3条）、闸门2b降级为WARN（第4条）。

2026-11-24 fixture 化（Chief/研判定口径）：原断言写死 72.2% / 9 只，账本每次成交都会
把它变红——脆弱根因是「断言绑本机账本当前值」。改为内存 fixture 账本喂 snapshot()，
断言派生关系（权威仓位 == fixture.combined.position_pct、持仓数 == fixture 非_带qty 条目数），
并参数化仓位 60.1/55.0/90.0 证明测试不绑账本。禁止读本机 holdings_levels.json。

共享脚本在仓库外 stock-team/monitor/，用 importlib 按路径加载。
"""
from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime
from pathlib import Path

import pytest

_MONITOR = Path(os.environ.get("STOCK_TEAM_MONITOR_DIR", str(Path(__file__).resolve().parents[3] / "monitor")))

# 这些脚本位于仓库外 stock-team/monitor/ 共享目录；本地/CI 无此目录时整模块跳过。
_REQUIRED = ("monitor_holdings.py", "daily_card.py", "check_holdings.py")
if any(not (_MONITOR / name).is_file() for name in _REQUIRED):
    pytest.skip(
        f"外部共享目录缺少 {', '.join(_REQUIRED)}（目录 {_MONITOR}）",
        allow_module_level=True,
    )


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


def _levels_fixture(position_pct=60.1, codes=("sz159845", "sz159934", "sh600000")):
    """内存账本 fixture：非 `_` 且带 qty 的条目 = 持仓；_meta.combined 权威字段可注入。"""
    levels = {
        "_meta": {
            "updated": "2026-11-24T21:42:00", "price_date": "2026-11-24",
            "combined": {
                "total_assets": 100000.0, "market_value": position_pct * 1000.0,
                "cash": (100.0 - position_pct) * 1000.0, "position_pct": position_pct,
            },
            "accounts": {},
        },
    }
    for c in codes:
        levels[c] = {"name": c, "qty": 100, "cost_avg": 2.0, "px": 2.5}
    return levels


def _isolate(mh, monkeypatch, levels=None):
    """注入报价/K线/账本 fixture，完全隔离本机真实数据。"""
    def fake_quote(code):
        return {"price": 2.5, "change_pct": 1.0, "open": 2.5, "prev_close": 2.475}

    monkeypatch.setattr(mh, "quote", fake_quote)
    monkeypatch.setattr(mh, "kline_last_day", lambda *a, **k: "2026-11-24")
    monkeypatch.setattr(mh, "LEVELS", levels if levels is not None else _levels_fixture())


# 仓位取 60.1（当前量级）/55.0/90.0（两端）——证明断言跟随 fixture、不绑任何账本当前值
_POSITION_CASES = [60.1, 55.0, 90.0]


class TestSnapshotReadsLevels:
    @pytest.mark.parametrize("pos", _POSITION_CASES)
    def test_position_split_estimate_vs_book(self, mh, monkeypatch, pos):
        levels = _levels_fixture(position_pct=pos)
        _isolate(mh, monkeypatch, levels)
        s = mh.snapshot("盘前")
        # 权威仓位派生自 fixture，不是硬编码；估算仓位（实时市值/实时总资产）单列
        assert s["position_pct"] is not None
        assert s["position_pct_book"] == pytest.approx(
            levels["_meta"]["combined"]["position_pct"], abs=1e-9
        )
        assert s["book_price_date"] == levels["_meta"]["price_date"]
        assert "price_date_source" in s

    @pytest.mark.parametrize("pos", _POSITION_CASES)
    def test_holdings_from_levels_not_portfolio(self, mh, monkeypatch, pos):
        levels = _levels_fixture(position_pct=pos)
        _isolate(mh, monkeypatch, levels)
        s = mh.snapshot("盘前")
        codes = {r["code"] for r in s["rows"]}
        expected = {c for c, v in levels.items() if not c.startswith("_") and isinstance(v, dict) and "qty" in v}
        assert codes == expected
        assert len(codes) == len(expected)  # 派生自 fixture 条目数，不写死 9/8 只
        assert "PORTFOLIO" not in s  # 结果集不含 portfolio 来源字段

    def test_no_portfolio_dependency(self, mh):
        # snapshot() 源码不再出现 PORTFOLIO 取数
        import inspect
        src = inspect.getsource(mh.snapshot)
        assert "PORTFOLIO.read_text" not in src


class TestCardShowsBothPositions:
    @pytest.mark.parametrize("pos", _POSITION_CASES)
    def test_card_labels_estimate_and_book(self, dc, mh, monkeypatch, pos):
        levels = _levels_fixture(position_pct=pos)
        _isolate(mh, monkeypatch, levels)
        snap = mh.snapshot("盘前")
        gate = {"ok": True, "problems": [], "price_date": "2026-11-24"}
        card = dc.build("盘前", snap, gate)
        pos_line = [line for line in card.splitlines() if line.startswith("仓位")][0]
        assert "估算" in pos_line
        assert "账本权威" in pos_line
        # 期望字符串派生自 fixture 权威仓位，卡片格式 `账本权威 {pos_book:.1f}%`
        assert f"账本权威 {pos:.1f}%" in pos_line


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
