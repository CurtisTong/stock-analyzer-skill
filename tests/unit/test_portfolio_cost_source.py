"""PortfolioManager cost_source 可追溯单元测试。

验证：
- add_position 新增持仓记录 cost_source（user_input / screenshot）
- add_position 加仓后 cost_source 自动置为 calculated
- update_position 更新 cost 时默认标记 cost_source=user_input
- oplog 记录 cost_before / cost_after / cost_source
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def mgr(tmp_path: Path, monkeypatch):
    from portfolio.manager import PortfolioManager
    from portfolio import oplog

    # 让 manager 内部 OpLog()（默认 data_dir()）落到临时目录，避免污染项目 data
    monkeypatch.setattr(oplog, "data_dir", lambda: tmp_path)
    data_file = tmp_path / "portfolio.json"
    data_file.write_text(json.dumps({"version": 2, "positions": [], "watchlist": []}))
    return PortfolioManager(str(data_file))


class TestCostSource:
    def test_add_new_position_keeps_user_source(self, mgr):
        mgr.add_position("sh600989", "宝丰能源", 18.5, 1000, cost_source="user_input")
        pos = mgr.get_position("sh600989")
        assert pos["cost_source"] == "user_input"

    def test_add_new_position_screenshot_source(self, mgr):
        mgr.add_position("sz002920", "德赛西威", 41.93, 200, cost_source="screenshot")
        pos = mgr.get_position("sz002920")
        assert pos["cost_source"] == "screenshot"

    def test_add_more_position_sets_calculated(self, mgr):
        mgr.add_position("sh600989", "宝丰能源", 18.5, 1000)
        mgr.add_position("sh600989", "宝丰能源", 24.02, 500)
        pos = mgr.get_position("sh600989")
        assert pos["cost_source"] == "calculated"
        assert pos["cost"] == round((18.5 * 1000 + 24.02 * 500) / 1500, 3)

    def test_update_cost_defaults_to_user_input(self, mgr):
        mgr.add_position("sh600989", "宝丰能源", 18.5, 1000)
        mgr.update_position("sh600989", cost=41.93)
        pos = mgr.get_position("sh600989")
        assert pos["cost"] == 41.93
        assert pos["cost_source"] == "user_input"

    def test_update_cost_explicit_source(self, mgr):
        mgr.add_position("sh600989", "宝丰能源", 18.5, 1000)
        mgr.update_position("sh600989", cost=41.93, cost_source="screenshot")
        assert mgr.get_position("sh600989")["cost_source"] == "screenshot"


class TestOplogCostTrace:
    def test_update_position_oplog_records_cost_before_after(self, mgr):
        mgr.add_position("sh600989", "宝丰能源", 18.5, 1000)
        mgr.update_position("sh600989", cost=41.93)
        from portfolio.oplog import OpLog

        ol = OpLog(str(mgr._path.parent / "portfolio_oplog.json"))
        history = ol.history()
        entry = next(e for e in history if e["op"] == "update_position")
        assert entry.get("cost_before") == 18.5
        assert entry.get("cost_after") == 41.93

    def test_add_position_oplog_records_source(self, mgr):
        mgr.add_position("sz002920", "德赛西威", 41.93, 200, cost_source="screenshot")
        from portfolio.oplog import OpLog

        ol = OpLog(str(mgr._path.parent / "portfolio_oplog.json"))
        entry = next(e for e in ol.history() if e["op"] == "add_position")
        assert entry.get("cost_source") == "screenshot"
        assert entry.get("cost_before") is None
        assert entry.get("cost_after") == 41.93

    def test_oplog_update_last_matches_op(self, mgr):
        from portfolio.oplog import OpLog

        ol = OpLog(str(mgr._path.parent / "portfolio_oplog.json"))
        ol.push("add_position", code="sh600989", extra={"cost_before": None})
        updated = ol.update_last(op="add_position", cost_after=18.5)
        assert updated["cost_after"] == 18.5
        # op 不匹配时拒绝回填
        assert ol.update_last(op="reduce_position", cost_after=9.9) is None
        last = ol.history()[-1]
        assert last.get("cost_after") == 18.5
