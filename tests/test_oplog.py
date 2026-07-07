"""Portfolio OpLog (undo) 单元测试。"""

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from portfolio.oplog import OpLog


class TestOpLog:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.path = self.tmp.name
        self.tmp.close()

    def teardown_method(self):
        Path(self.path).unlink(missing_ok=True)

    def test_push_and_history(self):
        """push 应记录到历史。"""
        ol = OpLog(self.path)
        ol.push("add_position", code="sh600989", snapshot_before={"positions": []})
        ol.push("reduce_position", code="sh600519", snapshot_before={"positions": [1]})
        history = ol.history()
        assert len(history) == 2
        assert history[0]["op"] == "add_position"
        assert history[1]["op"] == "reduce_position"

    def test_undo_returns_snapshot(self):
        """undo 应返回最近操作前的快照。"""
        ol = OpLog(self.path)
        snapshot = {"positions": ["sh600989"], "version": 2}
        ol.push("add_position", code="sh600989", snapshot_before=snapshot)
        restored = ol.undo()
        assert restored == snapshot

    def test_undo_empty_returns_none(self):
        """空历史 undo 返回 None。"""
        ol = OpLog(self.path)
        assert ol.undo() is None

    def test_peek_does_not_remove(self):
        """peek 仅查看，不删除。"""
        ol = OpLog(self.path)
        ol.push("add_position", code="sh600519")
        first = ol.peek()
        second = ol.peek()
        assert first == second
        assert len(ol.history()) == 1

    def test_max_history_trim(self):
        """超过最大历史条数时旧条目被剔除。"""
        ol = OpLog(self.path)
        for i in range(60):
            ol.push(f"op_{i}", code=f"sh{600000 + i}")
        history = ol.history()
        # 默认保留 50 条
        assert len(history) <= 50

    def test_clear_resets_history(self):
        """clear 清空操作历史。"""
        ol = OpLog(self.path)
        ol.push("add_position", code="sh600519")
        ol.clear()
        assert ol.history() == []

    def test_persistence(self):
        """应持久化到文件。"""
        ol1 = OpLog(self.path)
        ol1.push("add_position", code="sh600989", snapshot_before={"x": 1})
        # 重新加载
        ol2 = OpLog(self.path)
        history = ol2.history()
        assert len(history) == 1
        assert history[0]["op"] == "add_position"
