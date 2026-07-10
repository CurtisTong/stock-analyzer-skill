"""
Sprint 5 选股快照系统测试（review#16）。
"""

import sys
import json
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from snapshots import (
    save_snapshot,
    load_snapshot,
    diff_snapshots,
    list_snapshots,
    _validate_strategy,
    _snapshot_path,
    main,
)  # noqa: E402


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
        assert data["version"] == "1.14.1"
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
        save_snapshot("balanced", rows, ["sh600519"])
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


# ═══════════════════════════════════════════════════════════════
# _validate_strategy：路径注入防护
# ═══════════════════════════════════════════════════════════════


class TestValidateStrategy:
    def test_valid_name_passes(self):
        """合法策略名应直接返回。"""
        _validate_strategy("balanced_v2")
        _validate_strategy("momentum-2025")
        _validate_strategy("low-vol")

    def test_empty_string_rejected(self):
        """空字符串应抛 ValueError。"""
        with pytest.raises(ValueError, match="非法策略名"):
            _validate_strategy("")

    def test_path_traversal_rejected(self):
        """包含 ../ 的策略名应被拒绝（防止路径遍历）。"""
        with pytest.raises(ValueError, match="非法策略名"):
            _validate_strategy("../etc/passwd")
        with pytest.raises(ValueError, match="非法策略名"):
            _validate_strategy("foo/bar")
        with pytest.raises(ValueError, match="非法策略名"):
            _validate_strategy("foo\\bar")

    def test_special_chars_rejected(self):
        """特殊字符应被拒绝。"""
        with pytest.raises(ValueError, match="非法策略名"):
            _validate_strategy("foo;bar")
        with pytest.raises(ValueError, match="非法策略名"):
            _validate_strategy("foo bar")
        with pytest.raises(ValueError, match="非法策略名"):
            _validate_strategy("foo$bar")


# ═══════════════════════════════════════════════════════════════
# _snapshot_path：路径构造
# ═══════════════════════════════════════════════════════════════


class TestSnapshotPath:
    def test_path_uses_data_dir(self, monkeypatch, tmp_path):
        """_snapshot_path 应基于 common.DATA_DIR 构造路径。"""
        from common import DATA_DIR as _real_data_dir

        monkeypatch.setattr("snapshots.DATA_DIR", str(tmp_path))
        # 注意：_snapshot_path 使用模块全局 DATA_DIR，需要 monkeypatch 该模块属性
        import snapshots

        monkeypatch.setattr(snapshots, "DATA_DIR", str(tmp_path))
        path = snapshots._snapshot_path("balanced", "2026-07-10", "abc123def456")
        assert (
            path
            == tmp_path / "snapshots" / "balanced" / "2026-07-10" / "abc123def456.json"
        )


# ═══════════════════════════════════════════════════════════════
# main：CLI 入口（list / diff / 无参数）
# ═══════════════════════════════════════════════════════════════


class TestMain:
    def test_no_args_prints_help(self, capsys, monkeypatch):
        """无参数时 main 应当打印 help 信息（含 list/diff 子命令）。"""
        monkeypatch.setattr(sys, "argv", ["snapshots.py"])
        main()  # 无 subcommand 时不抛 SystemExit
        captured = capsys.readouterr()
        # 帮助信息会列出子命令
        assert "list" in captured.out
        assert "diff" in captured.out

    def test_diff_command_text_output(self, temp_snapshots_dir, capsys, monkeypatch):
        """diff 子命令文本输出格式正确。"""
        rows_a = [_make_row("sh600519", "贵州茅台", 80.0)]
        rows_b = [
            _make_row("sh600519", "贵州茅台", 85.0),
            _make_row("sh600000", "浦发银行", 70.0),
        ]
        p_a = save_snapshot("balanced", rows_a, ["sh600519"])
        p_b = save_snapshot("balanced", rows_b, ["sh600519", "sh600000"])

        monkeypatch.setattr(sys, "argv", ["snapshots.py", "diff", str(p_a), str(p_b)])
        main()
        captured = capsys.readouterr()
        assert "新增" in captured.out
        assert "退出" in captured.out
        assert "分数变化" in captured.out

    def test_diff_command_json_output(self, temp_snapshots_dir, capsys, monkeypatch):
        """diff 子命令 JSON 输出格式正确。"""
        rows_a = [_make_row("sh600519", "贵州茅台", 80.0)]
        rows_b = [_make_row("sh600519", "贵州茅台", 85.0)]
        p_a = save_snapshot("balanced", rows_a, ["sh600519"])
        p_b = save_snapshot("balanced", rows_b, ["sh600519"])

        monkeypatch.setattr(
            sys, "argv", ["snapshots.py", "diff", str(p_a), str(p_b), "--json"]
        )
        main()
        captured = capsys.readouterr()
        # 输出必须是合法 JSON
        parsed = json.loads(captured.out)
        assert "added" in parsed
        assert "removed" in parsed
        assert "score_changes" in parsed
