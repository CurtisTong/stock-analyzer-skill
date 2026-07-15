"""portfolio/manager.py 覆盖测试。

补充覆盖 undo、oplog_history、update_position、tag/untag_position、
add/remove_watch、check_concentration（行情口径）、risk_summary、
attribution_report、atomic_update、_push_oplog 等方法。
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from portfolio.manager import PortfolioManager


def _make_portfolio(tmp_path: Path, initial: dict = None) -> PortfolioManager:
    data_file = tmp_path / "portfolio.json"
    if initial is None:
        initial = {"version": 2, "positions": [], "watchlist": []}
    data_file.write_text(json.dumps(initial, ensure_ascii=False), encoding="utf-8")
    return PortfolioManager(path=str(data_file))


def _make_portfolio_with_oplog(tmp_path, monkeypatch):
    """构造 manager 并将 oplog 路径重定向到临时目录。"""
    import portfolio.oplog as oplog_mod

    oplog_file = tmp_path / "portfolio_oplog.json"
    monkeypatch.setattr(oplog_mod, "_oplog_path", lambda: oplog_file)
    return _make_portfolio(tmp_path)


class TestUndoRedo:
    def test_undo_empty_returns_none(self, tmp_path, monkeypatch):
        mgr = _make_portfolio_with_oplog(tmp_path, monkeypatch)
        assert mgr.undo() is None

    def test_undo_restores_previous(self, tmp_path, monkeypatch):
        mgr = _make_portfolio_with_oplog(tmp_path, monkeypatch)
        mgr.add_position("sh600519", "茅台", 100, 100)
        assert len(mgr.get_positions()) == 1
        result = mgr.undo()
        assert result is not None
        assert result["restored"] is True
        assert len(mgr.get_positions()) == 0

    def test_undo_after_multiple_ops(self, tmp_path, monkeypatch):
        mgr = _make_portfolio_with_oplog(tmp_path, monkeypatch)
        mgr.add_position("sh600519", "茅台", 100, 100)
        mgr.add_position("sh600001", "浦发", 10, 100)
        assert len(mgr.get_positions()) == 2
        mgr.undo()  # 撤销最后一次 add
        assert len(mgr.get_positions()) == 1
        assert mgr.get_positions()[0]["code"] == "sh600519"

    def test_undo_exception_returns_none(self, tmp_path, monkeypatch):
        mgr = _make_portfolio_with_oplog(tmp_path, monkeypatch)
        with patch("portfolio.oplog.OpLog.undo", side_effect=RuntimeError("err")):
            assert mgr.undo() is None

    def test_oplog_history(self, tmp_path, monkeypatch):
        mgr = _make_portfolio_with_oplog(tmp_path, monkeypatch)
        mgr.add_position("sh600519", "茅台", 100, 100)
        history = mgr.oplog_history(limit=5)
        assert isinstance(history, list)
        assert len(history) >= 1

    def test_oplog_history_exception(self, tmp_path, monkeypatch):
        mgr = _make_portfolio_with_oplog(tmp_path, monkeypatch)
        with patch("portfolio.oplog.OpLog.history", side_effect=RuntimeError("err")):
            assert mgr.oplog_history() == []


class TestUpdatePosition:
    def test_update_fields(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [
                    {
                        "code": "sh600519",
                        "name": "茅台",
                        "cost": 100,
                        "quantity": 100,
                        "tags": [],
                    }
                ],
                "watchlist": [],
            },
        )
        result = mgr.update_position(
            "sh600519",
            cost=110,
            quantity=200,
            name="贵州茅台",
            buy_date="2025-01-01",
            tags=["白酒"],
        )
        assert result["cost"] == 110
        assert result["quantity"] == 200
        assert result["name"] == "贵州茅台"
        assert result["buy_date"] == "2025-01-01"
        assert result["tags"] == ["白酒"]

    def test_update_nonexistent(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        result = mgr.update_position("sh600519", cost=110)
        assert result is None

    def test_update_no_save(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [
                    {
                        "code": "sh600519",
                        "name": "茅台",
                        "cost": 100,
                        "quantity": 100,
                        "tags": [],
                    }
                ],
                "watchlist": [],
            },
        )
        mgr.update_position("sh600519", cost=110, auto_save=False)
        # 未保存，内存中已更新
        assert mgr.get_position("sh600519")["cost"] == 110


class TestTagUntagPosition:
    def test_tag_position(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [
                    {
                        "code": "sh600519",
                        "name": "茅台",
                        "cost": 100,
                        "quantity": 100,
                        "tags": [],
                    }
                ],
                "watchlist": [],
            },
        )
        mgr.tag_position("sh600519", "白酒", "龙头")
        pos = mgr.get_position("sh600519")
        assert "白酒" in pos["tags"]
        assert "龙头" in pos["tags"]

    def test_tag_position_appends(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [
                    {
                        "code": "sh600519",
                        "name": "茅台",
                        "cost": 100,
                        "quantity": 100,
                        "tags": ["白酒"],
                    }
                ],
                "watchlist": [],
            },
        )
        mgr.tag_position("sh600519", "龙头")
        pos = mgr.get_position("sh600519")
        assert "龙头" in pos["tags"]
        assert "白酒" in pos["tags"]

    def test_tag_nonexistent(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        assert mgr.tag_position("sh600519", "x") is None

    def test_untag_position(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [
                    {
                        "code": "sh600519",
                        "name": "茅台",
                        "cost": 100,
                        "quantity": 100,
                        "tags": ["白酒", "龙头"],
                    }
                ],
                "watchlist": [],
            },
        )
        mgr.untag_position("sh600519", "龙头")
        pos = mgr.get_position("sh600519")
        assert "龙头" not in pos["tags"]
        assert "白酒" in pos["tags"]

    def test_untag_nonexistent_tag(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [
                    {
                        "code": "sh600519",
                        "name": "茅台",
                        "cost": 100,
                        "quantity": 100,
                        "tags": ["白酒"],
                    }
                ],
                "watchlist": [],
            },
        )
        mgr.untag_position("sh600519", "不存在")
        pos = mgr.get_position("sh600519")
        assert pos["tags"] == ["白酒"]


class TestWatchOperations:
    def test_add_watch_new(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        result = mgr.add_watch("sz000858", "五粮液", target_buy=70, target_sell=90)
        assert result["code"] == "sz000858"
        assert result["name"] == "五粮液"
        assert result["target_buy"] == 70
        assert mgr.get_watch("sz000858") is not None

    def test_add_watch_updates_existing(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [],
                "watchlist": [
                    {"code": "sz000858", "name": "", "target_buy": 0, "target_sell": 0}
                ],
            },
        )
        mgr.add_watch("sz000858", "五粮液", target_buy=70)
        w = mgr.get_watch("sz000858")
        assert w["name"] == "五粮液"
        assert w["target_buy"] == 70

    def test_remove_watch(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        mgr.add_watch("sz000858", "五粮液")
        assert mgr.remove_watch("sz000858") is True
        assert mgr.get_watch("sz000858") is None

    def test_remove_watch_not_found(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        assert mgr.remove_watch("sz000858") is False

    def test_get_all_codes(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [
                    {
                        "code": "sh600519",
                        "name": "茅台",
                        "cost": 100,
                        "quantity": 100,
                        "tags": [],
                    }
                ],
                "watchlist": [
                    {
                        "code": "sz000858",
                        "name": "五粮液",
                        "target_buy": 0,
                        "target_sell": 0,
                    }
                ],
            },
        )
        codes = mgr.get_all_codes()
        assert "sh600519" in codes
        assert "sz000858" in codes


class TestCheckConcentration:
    def test_empty_positions(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        result = mgr.check_concentration()
        assert result == {"warnings": [], "details": {}}

    def test_cost_basis(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [
                    {
                        "code": "sh600519",
                        "name": "茅台",
                        "cost": 100,
                        "quantity": 100,
                        "tags": ["白酒"],
                    },
                    {
                        "code": "sh600001",
                        "name": "浦发",
                        "cost": 10,
                        "quantity": 100,
                        "tags": ["银行"],
                    },
                ],
                "watchlist": [],
            },
        )
        result = mgr.check_concentration()
        # 茅台占比 10000/11000 ≈ 90.9% > 20%
        assert any("单一标的" in w for w in result["warnings"])
        assert "single" in result["details"]

    def test_market_value_basis(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [
                    {
                        "code": "sh600519",
                        "name": "茅台",
                        "cost": 100,
                        "quantity": 100,
                        "tags": ["白酒"],
                    },
                    {
                        "code": "sh600001",
                        "name": "浦发",
                        "cost": 10,
                        "quantity": 100,
                        "tags": ["银行"],
                    },
                ],
                "watchlist": [],
            },
        )
        result = mgr.check_concentration(quotes={"sh600519": 120, "sh600001": 8})
        assert "single" in result["details"]

    def test_industry_concentration_warning(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [
                    {
                        "code": "sh600519",
                        "name": "茅台",
                        "cost": 100,
                        "quantity": 100,
                        "tags": ["白酒"],
                    },
                    {
                        "code": "sz000858",
                        "name": "五粮液",
                        "cost": 100,
                        "quantity": 100,
                        "tags": ["白酒"],
                    },
                ],
                "watchlist": [],
            },
        )
        result = mgr.check_concentration(industry_limit=0.5)
        # 白酒行业占比 100% > 50%
        assert any("行业集中度" in w for w in result["warnings"])

    def test_top3_concentration(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [
                    {
                        "code": f"sh60000{i}",
                        "name": f"S{i}",
                        "cost": 100,
                        "quantity": 100,
                        "tags": [],
                    }
                    for i in range(4)
                ],
                "watchlist": [],
            },
        )
        result = mgr.check_concentration(top3_limit=0.5)
        # 4 只均匀持仓，top3 = 75% > 50%
        assert any("前3大" in w for w in result["warnings"])

    def test_zero_total_value(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [
                    {
                        "code": "sh600519",
                        "name": "茅台",
                        "cost": 0,
                        "quantity": 0,
                        "tags": [],
                    }
                ],
                "watchlist": [],
            },
        )
        result = mgr.check_concentration()
        assert result == {"warnings": [], "details": {}}


class TestRiskSummary:
    def test_no_positions(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        assert mgr.risk_summary() == "暂无持仓"

    def test_import_error(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [
                    {
                        "code": "sh600519",
                        "name": "茅台",
                        "cost": 100,
                        "quantity": 100,
                        "tags": [],
                    }
                ],
                "watchlist": [],
            },
        )
        with patch.dict("sys.modules", {"business.risk_metrics": None}):
            result = mgr.risk_summary()
        assert "不可用" in result

    def test_with_positions(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [
                    {
                        "code": "sh600519",
                        "name": "茅台",
                        "cost": 100,
                        "quantity": 100,
                        "tags": ["白酒"],
                    }
                ],
                "watchlist": [],
            },
        )
        fake_result = {
            "var_pct": 3.5,
            "cvar_pct": 4.2,
            "worst_scenarios": [
                {"code": "sh600519", "name": "茅台", "weight": 1.0, "var_1d_pct": 3.5},
            ],
        }
        with patch(
            "business.risk_metrics.position_var_summary", return_value=fake_result
        ):
            result = mgr.risk_summary(quotes={"sh600519": 120})
        assert "组合风险摘要" in result
        assert "VaR" in result
        assert "茅台" in result

    def test_zero_total_value(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [
                    {
                        "code": "sh600519",
                        "name": "茅台",
                        "cost": 0,
                        "quantity": 0,
                        "tags": [],
                    }
                ],
                "watchlist": [],
            },
        )
        result = mgr.risk_summary()
        assert "≤ 0" in result


class TestAttributionReport:
    def test_no_positions(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        assert mgr.attribution_report() == "暂无持仓"

    def test_import_error(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [
                    {
                        "code": "sh600519",
                        "name": "茅台",
                        "cost": 100,
                        "quantity": 100,
                        "tags": [],
                    }
                ],
                "watchlist": [],
            },
        )
        with patch.dict("sys.modules", {"portfolio.brinson": None}):
            result = mgr.attribution_report()
        assert "不可用" in result


class TestAtomicUpdate:
    def test_atomic_update(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [],
                "watchlist": [],
            },
        )

        def _add(d):
            d.setdefault("positions", []).append(
                {"code": "sh600519", "name": "茅台", "cost": 100, "quantity": 100}
            )
            return d

        mgr.atomic_update(_add)
        assert len(mgr.get_positions()) == 1

    def test_to_dict(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [
                    {
                        "code": "sh600519",
                        "name": "茅台",
                        "cost": 100,
                        "quantity": 100,
                        "tags": [],
                    }
                ],
                "watchlist": [{"code": "sz000858", "name": "五粮液"}],
            },
        )
        d = mgr.to_dict()
        assert "positions" in d
        assert "watchlist" in d
        assert len(d["positions"]) == 1

    def test_summary(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [
                    {
                        "code": "sh600519",
                        "name": "茅台",
                        "cost": 100,
                        "quantity": 100,
                        "tags": [],
                    }
                ],
                "watchlist": [{"code": "sz000858", "name": "五粮液"}],
            },
        )
        s = mgr.summary()
        assert "持仓 1 只" in s
        assert "自选 1 只" in s
        assert "茅台" in s

    def test_export_codes(self, tmp_path):
        mgr = _make_portfolio(
            tmp_path,
            initial={
                "version": 2,
                "positions": [
                    {
                        "code": "sh600519",
                        "name": "茅台",
                        "cost": 100,
                        "quantity": 100,
                        "tags": [],
                    }
                ],
                "watchlist": [],
            },
        )
        assert mgr.export_codes() == ["sh600519"]

    def test_data_path_property(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        assert "portfolio.json" in mgr.data_path

    def test_portfolio_type_property(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        assert mgr.portfolio_type == "实盘持仓"
