"""
Sprint 5 选股快照系统测试（review#16）。
"""

import sys
import json
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from snapshots import save_snapshot, load_snapshot, diff_snapshots, list_snapshots  # noqa: E402


def _make_row(code, name, score, **kwargs):
    return {
        "code": code,
        "name": name,
        "score": score,
        "industry": kwargs.get("industry", "默认"),
        "board": kwargs.get("board", "主板"),
        "quality": kwargs.get("quality", 50),
        "valuation": kwargs.get("valuation", 50),
        "momentum": kwargs.get("momentum", 50),
        "liquidity": kwargs.get("liquidity", 50),
        "volatility": kwargs.get("volatility", 50),
        "dividend": kwargs.get("dividend", 50),
        "price": kwargs.get("price", 10.0),
        "change_pct": kwargs.get("change_pct", 0.0),
        "pe": kwargs.get("pe", 15.0),
        "pb": kwargs.get("pb", 2.0),
        "roe": kwargs.get("roe", 10.0),
        "rejected": kwargs.get("rejected", []),
    }


@pytest.fixture
def temp_snapshots_dir(monkeypatch):
    """临时快照目录（隔离真实 DATA_DIR）。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        from common import DATA_DIR as _real_dir
        # 临时覆盖 DATA_DIR（snapshots 内部用 Path(DATA_DIR) 计算）
        import snapshots as _s
        monkeypatch.setattr(_s, "DATA_DIR", tmpdir)
        yield tmpdir


class TestSaveSnapshot:
    """保存快照测试。"""

    def test_save_creates_file(self, temp_snapshots_dir):
        rows = [_make_row("sh600519", "贵州茅台", 80.0)]
        path = save_snapshot("balanced", rows, ["sh600519"], regime="range")
        assert path.exists()
        assert path.suffix == ".json"
        assert "balanced" in str(path)
        assert "sh600519" not in str(path)  # hash 文件名，不是 code

    def test_save_includes_metadata(self, temp_snapshots_dir):
        rows = [_make_row("sh600519", "贵州茅台", 80.0)]
        path = save_snapshot("balanced", rows, ["sh600519"], regime="bull")
        data = load_snapshot(path)
        assert data["version"] == "1.0.0"
        assert data["strategy"] == "balanced"
        assert data["regime"] == "bull"
        assert data["pool_size"] == 1
        assert data["result_size"] == 1
        assert "timestamp" in data
        assert "date" in data

    def test_save_multiple_codes(self, temp_snapshots_dir):
        rows = [
            _make_row("sh600519", "贵州茅台", 90.0),
            _make_row("sh600989", "宝钢股份", 80.0),
        ]
        path = save_snapshot("balanced", rows, ["sh600519", "sh600989"])
        data = load_snapshot(path)
        assert data["result_size"] == 2
        assert {r["code"] for r in data["rows"]} == {"sh600519", "sh600989"}

    def test_save_with_extra(self, temp_snapshots_dir):
        rows = [_make_row("sh600519", "贵州茅台", 80.0)]
        path = save_snapshot(
            "balanced", rows, ["sh600519"], extra={"note": "test snapshot"}
        )
        data = load_snapshot(path)
        assert data["extra"]["note"] == "test snapshot"

    def test_save_includes_factor_breakdown(self, temp_snapshots_dir):
        """快照应包含 6 因子分。"""
        row = _make_row("sh600519", "贵州茅台", 80.0, quality=70, valuation=60)
        path = save_snapshot("balanced", [row], ["sh600519"])
        data = load_snapshot(path)
        saved = data["rows"][0]
        assert saved["quality"] == 70
        assert saved["valuation"] == 60


class TestListSnapshots:
    """列出快照测试。"""

    def test_list_empty(self, temp_snapshots_dir):
        assert list_snapshots() == []

    def test_list_returns_sorted_by_mtime(self, temp_snapshots_dir):
        rows = [_make_row("sh600519", "贵州茅台", 80.0)]
        p1 = save_snapshot("balanced", rows, ["sh600519"])
        rows2 = [_make_row("sh600989", "宝钢股份", 70.0)]
        p2 = save_snapshot("balanced", rows2, ["sh600989"])
        files = list_snapshots()
        assert len(files) >= 2
        # 最近的（p2）应在最前
        assert files[0] == p2

    def test_list_filter_by_strategy(self, temp_snapshots_dir):
        rows = [_make_row("sh600519", "贵州茅台", 80.0)]
        save_snapshot("balanced", rows, ["sh600519"])
        rows2 = [_make_row("sh600989", "宝钢股份", 70.0)]
        save_snapshot("growth_momentum", rows2, ["sh600989"])
        files = list_snapshots(strategy="balanced")
        assert all("balanced" in str(f) for f in files)


class TestDiffSnapshots:
    """对比快照测试。"""

    def test_diff_added_removed(self, temp_snapshots_dir):
        """A 期不含的 code → B 期新增。"""
        rows_a = [_make_row("sh600519", "贵州茅台", 80.0)]
        rows_b = [
            _make_row("sh600519", "贵州茅台", 80.0),
            _make_row("sh600989", "宝钢股份", 70.0),
        ]
        p_a = save_snapshot("balanced", rows_a, ["sh600519"])
        p_b = save_snapshot("balanced", rows_b, ["sh600519", "sh600989"])
        diff = diff_snapshots(p_a, p_b)
        assert "sh600989" in diff["added"]
        assert diff["removed"] == []

    def test_diff_score_changes(self, temp_snapshots_dir):
        rows_a = [_make_row("sh600519", "贵州茅台", 80.0)]
        rows_b = [_make_row("sh600519", "贵州茅台", 85.0)]
        p_a = save_snapshot("balanced", rows_a, ["sh600519"])
        p_b = save_snapshot("balanced", rows_b, ["sh600519"])
        diff = diff_snapshots(p_a, p_b)
        assert len(diff["score_changes"]) == 1
        change = diff["score_changes"][0]
        assert change["code"] == "sh600519"
        assert change["delta"] == 5.0

    def test_diff_metadata(self, temp_snapshots_dir):
        rows = [_make_row("sh600519", "贵州茅台", 80.0)]
        p_a = save_snapshot("balanced", rows, ["sh600519"], regime="range")
        p_b = save_snapshot("balanced", rows, ["sh600519"], regime="bull")
        diff = diff_snapshots(p_a, p_b)
        assert diff["strategy_a"] == "balanced"
        assert diff["strategy_b"] == "balanced"
        assert diff["timestamp_a"] != diff["timestamp_b"]
