"""Portfolio OpLog (undo) 单元测试。"""

import json
import sys
import tempfile
import threading
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

    def test_corrupted_json_fallback(self):
        """_load 读取损坏 JSON 时回退到空记录。"""
        Path(self.path).write_text("{invalid json!!!", encoding="utf-8")
        ol = OpLog(self.path)
        assert ol.history() == []

    def test_concurrent_push_no_loss(self):
        """并发 push 不丢失记录（验证 file_lock 保护读-改-写）。"""
        ol = OpLog(self.path)
        n_threads = 10
        n_per_thread = 5

        def worker(tid: int):
            for i in range(n_per_thread):
                ol.push("add_position", code=f"sh{600000 + tid * 100 + i}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 重新加载确认持久化结果（history 默认只返回最近 20 条，用 limit 扩大范围）
        ol2 = OpLog(self.path)
        assert len(ol2.history(limit=100)) == n_threads * n_per_thread

    def test_concurrent_push_undo_safe(self):
        """并发 push + undo 不损坏文件（文件始终是合法 JSON）。"""
        ol = OpLog(self.path)
        # 预填一些记录
        for i in range(5):
            ol.push("add_position", code=f"sh{600000 + i}", snapshot_before={"i": i})

        errors = []

        def pusher():
            try:
                for i in range(10):
                    ol.push("add_position", code=f"sh{700000 + i}")
            except Exception as e:
                errors.append(e)

        def undoer():
            try:
                for _ in range(5):
                    ol.undo()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=pusher), threading.Thread(target=undoer)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        # 文件始终可被正常解析
        data = json.loads(Path(self.path).read_text(encoding="utf-8"))
        assert "entries" in data
