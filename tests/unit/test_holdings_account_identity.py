"""持仓闸门账户级恒等校验测试（hermetic：tmp_path 构造账本，不读真实持仓）。

2026-11-23 实盘 bug：账本重建只更新 combined、忘同步 accounts，账户字段还是旧值
（ta≠mv+cash、pct 记 94.3% 实算 78%），但闸门只查 combined，7 项全绿漏检。
本测试锁定新增的账户级四项校验：内部资金恒等、仓位自洽、与 combined 对齐、字段缺失。

check_holdings.py 位于仓库外共享目录 stock-team/monitor/，用 importlib 按路径加载。
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path

import pytest

_MONITOR = Path(__file__).resolve().parents[3] / "monitor" / "check_holdings.py"
_NOW = datetime(2026, 11, 23, 23, 45)


@pytest.fixture(scope="module")
def ch():
    spec = importlib.util.spec_from_file_location("check_holdings_under_test", _MONITOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _base_ledger():
    """构造一份账户级完全自洽的最小账本。"""
    return {
        "_meta": {
            "updated": "2026-11-23T23:42:00",
            "price_date": "2026-11-23",
            "accounts": {
                "5938": {
                    "broker": "A", "total_assets": 424415.95, "market_value": 306583.20,
                    "cash_available": 117832.75, "position_pct": 72.2, "day_pnl": None,
                },
                "5331": {
                    "broker": "B", "total_assets": 282943.97, "market_value": 204388.80,
                    "cash_available": 78555.17, "position_pct": 72.2, "day_pnl": None,
                },
            },
            "combined": {
                "total_assets": 707359.92, "market_value": 510972.0, "cash": 196387.92,
                "position_pct": 72.2, "day_pnl": None, "day_pnl_pct": None, "float_pnl": None,
            },
        },
        "sh600000": {"name": "测试A", "qty": 10000, "cost_avg": 10.0, "px": 20.0,
                     "pct_of_assets": 28.27, "accounts": {"5938": 10000}},
        "sz000001": {"name": "测试B", "qty": 15539, "cost_avg": 20.0, "px": 20.0,
                     "pct_of_assets": 43.93, "accounts": {"5331": 15539}},
    }


def _run(ch, tmp_path, ledger, **kw):
    p = tmp_path / "holdings.json"
    p.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
    return ch.check(p, now=_NOW, price_date="2026-11-23", **kw)


class TestAccountIdentityClean:
    def test_consistent_accounts_pass(self, ch, tmp_path):
        r = _run(ch, tmp_path, _base_ledger())
        acct_problems = [p for p in r["problems"] if "账户" in p["item"]]
        assert acct_problems == [], acct_problems
        assert r["ok"] is True

    def test_legitimate_zero_cash_not_flagged(self, ch, tmp_path):
        # 合法场景：某账户满仓 cash≈0、ta==mv，不判 FAIL
        led = _base_ledger()
        a = led["_meta"]["accounts"]["5331"]
        a["market_value"] = 282943.97
        a["cash_available"] = 0.0
        a["total_assets"] = 282943.97
        a["position_pct"] = 100.0
        # combined 同步
        led["_meta"]["combined"]["market_value"] = 306583.20 + 282943.97
        led["_meta"]["combined"]["cash"] = 117832.75
        led["_meta"]["combined"]["position_pct"] = round(589527.17 / 707359.92 * 100, 1)
        r = _run(ch, tmp_path, led)
        # 只确认该账户不因 cash=0 被误报资金恒等
        assert not [p for p in r["problems"] if p["item"] == "账户资金恒等" and "5331" in p["detail"]]


class TestAccountIdentityDirty:
    def test_account_cash_identity_drift_fails(self, ch, tmp_path):
        led = _base_ledger()
        led["_meta"]["accounts"]["5938"]["cash_available"] = 100000.0  # ta≠mv+cash
        r = _run(ch, tmp_path, led)
        assert any(p["item"] == "账户资金恒等" and "5938" in p["detail"] for p in r["problems"])
        assert r["ok"] is False

    def test_account_pct_stale_fails(self, ch, tmp_path):
        led = _base_ledger()
        led["_meta"]["accounts"]["5331"]["position_pct"] = 99.7  # 实算 72.2
        r = _run(ch, tmp_path, led)
        assert any(p["item"] == "账户仓位自洽" and "5331" in p["detail"] for p in r["problems"])
        assert r["ok"] is False

    def test_account_vs_combined_mv_drift_fails(self, ch, tmp_path):
        led = _base_ledger()
        # 账户 mv 停在旧值（加总≠combined），模拟 11-23 重建只更新 combined
        led["_meta"]["accounts"]["5938"]["market_value"] = 387838.80
        led["_meta"]["accounts"]["5331"]["market_value"] = 276843.00
        r = _run(ch, tmp_path, led)
        assert any(p["item"] == "账户对齐combined" and "市值" in p["detail"] for p in r["problems"])
        assert r["ok"] is False

    def test_missing_account_field_fails(self, ch, tmp_path):
        led = _base_ledger()
        del led["_meta"]["accounts"]["5331"]["cash_available"]
        r = _run(ch, tmp_path, led)
        assert any(p["item"] == "账户字段" and "5331" in p["detail"] for p in r["problems"])
        assert r["ok"] is False
