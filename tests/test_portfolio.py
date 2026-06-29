"""
portfolio/manager.py 单元测试：覆盖持仓 CRUD、自选 CRUD、v1 迁移、原子写。
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from portfolio.manager import PortfolioManager  # noqa: E402


def _make_portfolio(tmp_path: Path, initial: dict = None) -> PortfolioManager:
    """构造一个使用临时文件作为存储的 PortfolioManager。

    默认创建空 v2 数据（不依赖 portfolio_example.json）。
    """
    data_file = tmp_path / "portfolio.json"
    if initial is None:
        initial = {"version": 2, "positions": [], "watchlist": []}
    data_file.write_text(json.dumps(initial, ensure_ascii=False), encoding="utf-8")
    return PortfolioManager(path=str(data_file))


# ═══════════════════════════════════════════════════════════════
# 1. 初始化与加载
# ═══════════════════════════════════════════════════════════════
class TestInit:
    def test_empty_file_creates_default(self, tmp_path):
        # 当 portfolio.json 不存在但 portfolio_example.json 存在时，
        # PortfolioManager 会回退到示例数据并把 is_example 设为 True。
        # 显式传入空数据确保测试与示例数据解耦。
        mgr = _make_portfolio(
            tmp_path, initial={"version": 2, "positions": [], "watchlist": []}
        )
        assert mgr.is_example is False
        assert mgr.get_positions() == []
        assert mgr.get_watchlist() == []

    def test_load_v2(self, tmp_path):
        initial = {
            "version": 2,
            "positions": [
                {
                    "code": "sh600989",
                    "name": "宝丰",
                    "cost": 20,
                    "quantity": 100,
                    "buy_date": "2025-01-01",
                    "tags": [],
                }
            ],
            "watchlist": [
                {
                    "code": "sz000858",
                    "name": "五粮液",
                    "target_buy": 0,
                    "target_sell": 0,
                    "added_date": "2025-01-01",
                }
            ],
        }
        mgr = _make_portfolio(tmp_path, initial)
        assert mgr.is_example is False
        assert len(mgr.get_positions()) == 1
        assert len(mgr.get_watchlist()) == 1

    def test_v1_migration(self, tmp_path):
        """v1 格式（只有 codes 列表）自动迁移为 v2。"""
        initial = {"codes": ["sh600989", "sz000858"]}
        mgr = _make_portfolio(tmp_path, initial)
        positions = mgr.get_positions()
        assert len(positions) == 2
        assert {p["code"] for p in positions} == {"sh600989", "sz000858"}
        # v1 字段缺失，应填默认值
        for p in positions:
            assert p["cost"] == 0
            assert p["quantity"] == 0
            assert p["tags"] == []


# ═══════════════════════════════════════════════════════════════
# 2. 持仓 CRUD
# ═══════════════════════════════════════════════════════════════
class TestPositionCRUD:
    def test_add_position(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        result = mgr.add_position(
            "sh600989", "宝丰能源", 20.0, 100, "2025-01-01", ["能源"]
        )
        assert result["code"] == "sh600989"
        assert result["cost"] == 20.0
        assert result["quantity"] == 100
        assert "能源" in result["tags"]

    def test_add_position_no_tags(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        result = mgr.add_position("sh600989", "宝丰", 20.0, 100)
        assert result["tags"] == []

    def test_add_existing_position_averages_cost(self, tmp_path):
        """加仓后应按加权平均成本计算。"""
        mgr = _make_portfolio(tmp_path)
        mgr.add_position("sh600989", "宝丰", 20.0, 100)
        # 加仓：再买 100 股 @ 30
        result = mgr.add_position("sh600989", "宝丰", 30.0, 100)
        # 加权：(20*100 + 30*100) / 200 = 25
        assert result["cost"] == 25.0
        assert result["quantity"] == 200

    def test_add_existing_position_merges_tags(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        mgr.add_position("sh600989", "宝丰", 20.0, 100, tags=["能源"])
        result = mgr.add_position("sh600989", "宝丰", 30.0, 100, tags=["长线", "能源"])
        assert set(result["tags"]) == {"能源", "长线"}

    def test_reduce_position_partial(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        mgr.add_position("sh600989", "宝丰", 20.0, 100)
        result = mgr.reduce_position("sh600989", 30)
        assert result["quantity"] == 70

    def test_reduce_position_to_zero_removes(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        mgr.add_position("sh600989", "宝丰", 20.0, 100)
        result = mgr.reduce_position("sh600989", 100)
        assert result is None
        assert mgr.get_position("sh600989") is None

    def test_reduce_position_more_than_held_removes(self, tmp_path):
        """减仓超过持仓也应正确移除。"""
        mgr = _make_portfolio(tmp_path)
        mgr.add_position("sh600989", "宝丰", 20.0, 100)
        # 减 200 > 100
        result = mgr.reduce_position("sh600989", 200)
        assert result is None
        assert mgr.get_position("sh600989") is None

    def test_reduce_position_invalid_quantity(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        with pytest.raises(ValueError):
            mgr.reduce_position("sh600989", 0)
        with pytest.raises(ValueError):
            mgr.reduce_position("sh600989", -10)

    def test_reduce_nonexistent_returns_none(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        assert mgr.reduce_position("sh000000", 10) is None

    def test_remove_position(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        mgr.add_position("sh600989", "宝丰", 20.0, 100)
        assert mgr.remove_position("sh600989") is True
        assert mgr.get_position("sh600989") is None

    def test_remove_nonexistent_returns_false(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        assert mgr.remove_position("sh000000") is False

    def test_update_position(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        mgr.add_position("sh600989", "宝丰", 20.0, 100)
        result = mgr.update_position("sh600989", cost=25.0, name="宝丰能源")
        assert result["cost"] == 25.0
        assert result["name"] == "宝丰能源"

    def test_update_nonexistent_returns_none(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        assert mgr.update_position("sh000000", cost=20.0) is None

    def test_get_position_case_insensitive(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        mgr.add_position("SH600989", "宝丰", 20.0, 100)
        assert mgr.get_position("sh600989") is not None
        assert mgr.get_position("SH600989") is not None


# ═══════════════════════════════════════════════════════════════
# 3. 标签管理
# ═══════════════════════════════════════════════════════════════
class TestTags:
    def test_tag_position(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        mgr.add_position("sh600989", "宝丰", 20.0, 100, tags=["能源"])
        result = mgr.tag_position("sh600989", "长线", "核心")
        assert set(result["tags"]) == {"能源", "长线", "核心"}

    def test_tag_position_idempotent(self, tmp_path):
        """重复 tag 不应重复添加。"""
        mgr = _make_portfolio(tmp_path)
        mgr.add_position("sh600989", "宝丰", 20.0, 100, tags=["能源"])
        mgr.tag_position("sh600989", "能源")
        assert mgr.get_position("sh600989")["tags"].count("能源") == 1

    def test_untag_position(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        mgr.add_position("sh600989", "宝丰", 20.0, 100, tags=["能源", "长线"])
        result = mgr.untag_position("sh600989", "能源")
        assert result["tags"] == ["长线"]

    def test_tag_nonexistent_returns_none(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        assert mgr.tag_position("sh000000", "tag") is None
        assert mgr.untag_position("sh000000", "tag") is None


# ═══════════════════════════════════════════════════════════════
# 4. 自选 CRUD
# ═══════════════════════════════════════════════════════════════
class TestWatchCRUD:
    def test_add_watch(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        result = mgr.add_watch("sz000858", "五粮液", target_buy=70.0, target_sell=90.0)
        assert result["code"] == "sz000858"
        assert result["target_buy"] == 70.0
        assert result["target_sell"] == 90.0
        assert "added_date" in result

    def test_add_watch_updates_existing(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        mgr.add_watch("sz000858", "五粮液", target_buy=70.0)
        result = mgr.add_watch("sz000858", "五粮液", target_sell=90.0)
        assert result["target_buy"] == 70.0
        assert result["target_sell"] == 90.0

    def test_remove_watch(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        mgr.add_watch("sz000858", "五粮液")
        assert mgr.remove_watch("sz000858") is True
        assert mgr.get_watch("sz000858") is None

    def test_remove_nonexistent_watch(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        assert mgr.remove_watch("sz000000") is False

    def test_get_watch_case_insensitive(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        mgr.add_watch("SZ000858", "五粮液")
        assert mgr.get_watch("sz000858") is not None


# ═══════════════════════════════════════════════════════════════
# 5. 跨操作
# ═══════════════════════════════════════════════════════════════
class TestCross:
    def test_get_all_codes(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        mgr.add_position("sh600989", "宝丰", 20.0, 100)
        mgr.add_watch("sz000858", "五粮液")
        codes = mgr.get_all_codes()
        assert "sh600989" in codes
        assert "sz000858" in codes
        assert len(codes) == 2

    def test_export_codes(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        mgr.add_position("sh600989", "宝丰", 20.0, 100)
        mgr.add_watch("sz000858", "五粮液")
        # export 只导出持仓，不包括自选
        assert mgr.export_codes() == ["sh600989"]

    def test_to_dict_returns_copy(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        mgr.add_position("sh600989", "宝丰", 20.0, 100)
        d = mgr.to_dict()
        d["positions"].clear()
        # 内部状态不应被影响
        assert len(mgr.get_positions()) == 1

    def test_summary(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        mgr.add_position("sh600989", "宝丰能源", 20.0, 100)
        mgr.add_watch("sz000858", "五粮液")
        s = mgr.summary()
        assert "持仓 1 只" in s
        assert "自选 1 只" in s
        assert "宝丰能源" in s
        assert "五粮液" in s

    def test_summary_empty(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        s = mgr.summary()
        assert "持仓 0 只" in s
        assert "自选 0 只" in s


# ═══════════════════════════════════════════════════════════════
# 6. 持久化
# ═══════════════════════════════════════════════════════════════
class TestPersistence:
    def test_save_writes_file(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        mgr.add_position("sh600989", "宝丰", 20.0, 100, auto_save=True)
        # 文件应被创建
        data_file = tmp_path / "portfolio.json"
        assert data_file.exists()
        # 内容可解析
        data = json.loads(data_file.read_text(encoding="utf-8"))
        assert data["version"] == 2
        assert len(data["positions"]) == 1

    def test_save_without_auto_save(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        mgr.add_position("sh600989", "宝丰", 20.0, 100, auto_save=False)
        # 内存中有，但未持久化
        assert len(mgr.get_positions()) == 1
        # 重新加载应为空
        mgr2 = _make_portfolio(tmp_path)
        assert len(mgr2.get_positions()) == 0

    def test_reload_after_save(self, tmp_path):
        mgr = _make_portfolio(tmp_path)
        mgr.add_position("sh600989", "宝丰", 20.0, 100)
        # 重新构造 manager（不复写文件）应能加载
        mgr2 = PortfolioManager(path=str(tmp_path / "portfolio.json"))
        assert mgr2.get_position("sh600989") is not None
