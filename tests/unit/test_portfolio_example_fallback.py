"""示例持仓回退写路径防护的不变量测试。

不变量：portfolio.json 不存在时，_load 回退示例数据仅用于展示
（"示例持仓"标签）；任何写操作（CRUD / undo）不得把示例数据
落盘到真实 / 虚拟 / 自定义路径——首条写入从空仓起步。

回归背景（2026-11-02 skill 审查 P0）：atomic_update 曾把示例数据
直接 _raw_write 回 portfolio.json，新装用户第一条 add_position
会把 5 只示例股 + 3 只示例自选写进真实持仓文件。
"""

from __future__ import annotations

import json

import pytest

from portfolio import PortfolioManager
from portfolio import crud

# 示例文件内容：两条示例持仓 + 一条示例自选，code 可与用户真实数据区分
EXAMPLE_DATA = {
    "version": 2,
    "positions": [
        {
            "code": "sh600519",
            "name": "示例贵州茅台",
            "cost": 1500.0,
            "quantity": 100,
            "buy_date": "2026-01-01",
            "tags": [],
        },
        {
            "code": "sz000001",
            "name": "示例平安银行",
            "cost": 10.0,
            "quantity": 1000,
            "buy_date": "2026-01-01",
            "tags": [],
        },
    ],
    "watchlist": [{"code": "sh601318", "name": "示例中国平安"}],
}

EXAMPLE_CODES = {p["code"] for p in EXAMPLE_DATA["positions"]}
NEW_CODE = "sz300274"


@pytest.fixture
def example_env(tmp_path, monkeypatch):
    """构造"目标文件不存在 + 示例文件存在"的隔离环境。

    manager / oplog / trade_log 各自绑定 data_dir，需同时 patch
    才能避免测试触碰真实用户数据（_data_dir 是 manager 内 import 期
    别名，须单独 patch）。
    """
    (tmp_path / "portfolio_example.json").write_text(json.dumps(EXAMPLE_DATA, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("portfolio.manager.data_dir", lambda: tmp_path)
    monkeypatch.setattr("portfolio.manager._data_dir", lambda: tmp_path)
    monkeypatch.setattr("portfolio.oplog.data_dir", lambda: tmp_path)
    monkeypatch.setattr("portfolio.trade_log.data_dir", lambda: tmp_path)
    return tmp_path


def _load_data(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TestExampleFallbackReadOnly:
    def test_read_falls_back_to_example(self, example_env):
        """展示路径保持原行为：回退示例数据 + 示例持仓标签。"""
        pm = PortfolioManager()
        assert pm.is_example is True
        assert pm.portfolio_type == "示例持仓"
        assert {p["code"] for p in pm.get_positions()} == EXAMPLE_CODES

    def test_first_add_starts_from_empty_not_example(self, example_env):
        """核心不变量：首条 add_position 落盘文件不含任何示例持仓。"""
        target = example_env / "portfolio.json"
        pm = PortfolioManager()
        crud.add_position(pm, NEW_CODE, "阳光电源", cost=120.0, quantity=100)

        assert target.exists()
        data = _load_data(target)
        codes = {p["code"] for p in data["positions"]}
        assert codes == {NEW_CODE}
        assert not (codes & EXAMPLE_CODES)
        # 示例自选同样不得混入
        assert data["watchlist"] == []

    def test_first_watch_write_starts_from_empty(self, example_env):
        """首条 add_watch 同样从空仓起步，示例持仓/自选不得落盘。"""
        target = example_env / "portfolio.json"
        pm = PortfolioManager()
        crud.add_watch(pm, "sh601899", name="紫金矿业")

        data = _load_data(target)
        assert [w["code"] for w in data["watchlist"]] == ["sh601899"]
        assert data["positions"] == []

    def test_undo_after_first_write_keeps_file_clean(self, example_env):
        """undo 恢复的快照不得是示例数据（快照按空仓记录）。"""
        target = example_env / "portfolio.json"
        pm = PortfolioManager()
        crud.add_position(pm, NEW_CODE, "阳光电源", cost=120.0, quantity=100)
        pm.undo()

        data = _load_data(target)
        codes = {p["code"] for p in data.get("positions", [])}
        assert not (codes & EXAMPLE_CODES)

    def test_virtual_first_write_starts_from_empty(self, example_env):
        """虚拟盘同样受保护：portfolio_virtual.json 首写不含示例数据。"""
        target = example_env / "portfolio_virtual.json"
        pm = PortfolioManager(virtual=True)
        assert pm.is_example is True
        crud.add_position(pm, NEW_CODE, "阳光电源", cost=120.0, quantity=100)

        data = _load_data(target)
        codes = {p["code"] for p in data["positions"]}
        assert codes == {NEW_CODE}

    def test_existing_file_not_affected(self, example_env, tmp_path, monkeypatch):
        """真实文件已存在时不走示例回退，加仓行为保持不变。"""
        target = tmp_path / "portfolio.json"
        target.write_text(
            json.dumps(
                {
                    "version": 2,
                    "positions": [
                        {
                            "code": NEW_CODE,
                            "name": "阳光电源",
                            "cost": 100.0,
                            "quantity": 50,
                            "buy_date": "2026-06-01",
                            "tags": [],
                        }
                    ],
                    "watchlist": [],
                }
            ),
            encoding="utf-8",
        )
        pm = PortfolioManager()
        assert pm.is_example is False
        crud.add_position(pm, NEW_CODE, "阳光电源", cost=120.0, quantity=50)

        data = _load_data(target)
        pos = next(p for p in data["positions"] if p["code"] == NEW_CODE)
        # 加权平均成本：(100*50 + 120*50) / 100 = 110
        assert pos["cost"] == pytest.approx(110.0)
        assert pos["quantity"] == 100
