"""账本重建流程封装单测（hermetic：内存账本 + tmp，不读真实持仓、不连网）。

2026-11-23 真实四笔交易重建验证：
  - 深100 清仓 54000@2.81、广合减 300@81.98、盛和减 800@13.8、取现 20000
  - 应重建出 9只 / 现金 196,387.92 / 市值 510,972 / 仓位 72.2% / 已实现 +3,162.20
  - 派生字段全重算：float_pnl 陈旧值修正、day_pnl 置 null、back_to_80pct 置 null（用null不用0）

rebuild_check.py 位于仓库外共享目录 stock-team/monitor/，用 importlib 按路径加载。
闸门验证走 check_holdings.check()（同一共享目录），用 tmp 文件、不碰生产账本。
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path

import pytest

_MONITOR = Path(os.environ.get("STOCK_TEAM_MONITOR_DIR", str(Path(__file__).resolve().parents[3] / "monitor")))
_BASE_BAK = _MONITOR / "holdings_levels_20261120.json.bak"

# 这些脚本位于仓库外 stock-team/monitor/ 共享目录；本地/CI 无此目录时整模块跳过，
# 避免污染 pytest tests/ 收集与 CI 门禁。设置 STOCK_TEAM_MONITOR_DIR 可指定目录。
_REQUIRED = ("rebuild_check.py", "check_holdings.py", "holdings_levels_20261120.json.bak")
if any(not (_MONITOR / name).is_file() for name in _REQUIRED):
    pytest.skip(
        f"外部共享目录缺少 {', '.join(_REQUIRED)}（目录 {_MONITOR}）",
        allow_module_level=True,
    )

_SPEC = importlib.util.spec_from_file_location("rebuild_check_under_test", _MONITOR / "rebuild_check.py")
rc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rc)

TRADES = [
    {"code": "sz159901", "delta_qty": -54000, "price": 2.81, "accounts": {"5938": -31700, "5331": -22300}},
    {"code": "sz001389", "delta_qty": -300, "price": 81.98, "accounts": {"5938": -300}},
    {"code": "sh600392", "delta_qty": -800, "price": 13.8, "accounts": {"5938": -800}},
]
NEW_PRICES = {
    "sz159845": 2.425, "sh588080": 1.257, "sh600989": 20.07, "sz159934": 7.726,
    "sz000807": 21.35, "sz300274": 70.23, "sz001389": 82.52, "sh600392": 13.77, "sh603799": 29.89,
}


@pytest.fixture
def base():
    return json.loads(_BASE_BAK.read_text(encoding="utf-8"))


def _rebuild(base, **kw):
    args = dict(price_date="2026-11-23", updated="2026-11-23T23:50:00", cash_adjustments=[-20000])
    args.update(kw)
    return rc.rebuild_from_trades(base, TRADES, NEW_PRICES, **args)


class TestRealFourTrades:
    def test_rebuilds_authoritative_ledger(self, base):
        led, val = _rebuild(base)
        c = led["_meta"]["combined"]
        assert c["total_assets"] == pytest.approx(707359.92, abs=0.01)
        assert c["market_value"] == pytest.approx(510972.00, abs=0.01)
        assert c["cash"] == pytest.approx(196387.92, abs=0.01)
        assert c["position_pct"] == pytest.approx(72.2, abs=0.05)

    def test_gate_all_green(self, base):
        led, val = _rebuild(base)
        assert val["ok"] is True
        assert val["failed"] == 0

    def test_nine_positions_deep100_cleared(self, base):
        led, val = _rebuild(base)
        positions = {k: v for k, v in led.items() if not k.startswith("_")}
        assert len(positions) == 9
        assert "sz159901" not in positions  # 深100 清仓
        assert positions["sz001389"]["qty"] == 300  # 广合 600→300
        assert positions["sh600392"]["qty"] == 800  # 盛和 1600→800

    def test_realized_pnl(self, base):
        led, val = _rebuild(base)
        assert led["_meta"]["combined"]["realized_20261123"] == pytest.approx(3162.20, abs=0.01)

    def test_account_mv_by_split_not_whole_qty(self, base):
        """账户市值按各股 accounts 拆分算，不是整只 qty 双记。"""
        led, val = _rebuild(base)
        acc = led["_meta"]["accounts"]
        # 科创50 5938:56400 / 5331:10000，宝丰 5938:2500/5331:1000
        assert acc["5938"]["market_value"] == pytest.approx(355198.80, abs=0.01)
        assert acc["5331"]["market_value"] == pytest.approx(155773.20, abs=0.01)
        assert acc["5938"]["market_value"] + acc["5331"]["market_value"] == pytest.approx(510972.00, abs=0.01)

    def test_derived_fields_fixed(self, base):
        """研判审计发现的陈旧派生字段被重算。"""
        led, val = _rebuild(base)
        c = led["_meta"]["combined"]
        assert c["float_pnl"] == pytest.approx(-63658.70, abs=0.01)  # 旧值 -76801 已修正
        assert c["day_pnl"] is None  # 旧值陈旧，置 null
        assert c["back_to_80pct_amount"] is None  # 仓位已<80%，字段不适用；用null不用0（0会被读成"卖0股回80%"）
        for acct in led["_meta"]["accounts"].values():
            assert acct["day_pnl"] is None


class TestBadDataFails:
    def test_split_mismatch_raises(self, base):
        bad = copy.deepcopy(TRADES)
        bad[0]["accounts"] = {"5938": -31700}  # 少 22300，拆分不平
        with pytest.raises(ValueError, match="拆分之和"):
            rc.rebuild_from_trades(base, bad, NEW_PRICES, price_date="2026-11-23", updated="x")

    def test_missing_new_price_raises(self, base):
        missing = {k: v for k, v in NEW_PRICES.items() if k != "sz159845"}
        with pytest.raises(ValueError, match="缺新价"):
            rc.rebuild_from_trades(base, TRADES, missing, price_date="2026-11-23", updated="x")

    def test_negative_qty_raises(self, base):
        bad = copy.deepcopy(TRADES)
        bad[0]["delta_qty"] = -999999  # 卖出超过持仓
        bad[0]["accounts"] = {"5938": -999999}
        with pytest.raises(ValueError, match="< 0"):
            rc.rebuild_from_trades(base, bad, NEW_PRICES, price_date="2026-11-23", updated="x")

    def test_new_buy_not_supported(self, base):
        bad = [{"code": "NEW", "delta_qty": 100, "price": 10.0, "accounts": {"5938": 100}}]
        with pytest.raises(ValueError, match="新买入"):
            rc.rebuild_from_trades(base, bad, NEW_PRICES, price_date="2026-11-23", updated="x")
