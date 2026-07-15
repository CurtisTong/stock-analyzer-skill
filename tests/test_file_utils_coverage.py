"""portfolio/_file_utils.py 覆盖测试。

mock 文件 I/O，覆盖 file_lock（含 stale lock 清理）、raw_write、atomic_write、
lock_path、data_dir、today 等函数。
"""

import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import portfolio._file_utils as fu


class TestDataDir:
    def test_data_dir_exists(self):
        d = fu.data_dir()
        assert d.name == "data"


class TestToday:
    def test_today_format(self):
        t = fu.today()
        assert len(t) == 10
        assert t[4] == "-" and t[7] == "-"


class TestLockPath:
    def test_lock_path(self, tmp_path):
        p = tmp_path / "portfolio.json"
        lp = fu.lock_path(p)
        assert lp.name == ".portfolio.lock"


class TestGetIntraLock:
    def test_same_path_returns_same_lock(self):
        l1 = fu._get_intra_lock("/tmp/x.lock")
        l2 = fu._get_intra_lock("/tmp/x.lock")
        assert l1 is l2

    def test_different_path_returns_different_lock(self):
        l1 = fu._get_intra_lock("/tmp/x.lock")
        l2 = fu._get_intra_lock("/tmp/y.lock")
        assert l1 is not l2


class TestRawWrite:
    def test_raw_write_creates_file(self, tmp_path):
        p = tmp_path / "data.json"
        fu.raw_write(p, {"a": 1})
        assert json.loads(p.read_text()) == {"a": 1}

    def test_raw_write_creates_parent_dir(self, tmp_path):
        p = tmp_path / "sub" / "data.json"
        fu.raw_write(p, {"a": 1})
        assert p.exists()

    def test_raw_write_overwrites(self, tmp_path):
        p = tmp_path / "data.json"
        fu.raw_write(p, {"a": 1})
        fu.raw_write(p, {"b": 2})
        assert json.loads(p.read_text()) == {"b": 2}


class TestAtomicWrite:
    def test_atomic_write(self, tmp_path):
        p = tmp_path / "data.json"
        fu.atomic_write(p, {"a": 1})
        assert json.loads(p.read_text()) == {"a": 1}

    def test_atomic_write_concurrent(self, tmp_path):
        """并发写入不应丢数据（文件锁保护）。"""
        p = tmp_path / "data.json"
        errors = []

        def _writer(val):
            try:
                for _ in range(5):
                    fu.atomic_write(p, {"v": val})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_writer, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        # 文件应是有效的 JSON
        assert json.loads(p.read_text())["v"] in range(4)


class TestFileLock:
    def test_file_lock_acquires_and_releases(self, tmp_path):
        p = tmp_path / "data.json"
        with fu.file_lock(p):
            # 锁文件应存在
            assert fu.lock_path(p).exists()
        # 退出后锁文件应被删除
        assert not fu.lock_path(p).exists()

    def test_file_lock_reentrant_same_thread(self, tmp_path):
        """同一线程可重复获取释放锁。"""
        p = tmp_path / "data.json"
        for _ in range(3):
            with fu.file_lock(p, timeout=2):
                assert fu.lock_path(p).exists()
        assert not fu.lock_path(p).exists()

    def test_stale_lock_cleaned_when_pid_dead(self, tmp_path):
        """锁文件 PID 已死时被清理。"""
        p = tmp_path / "data.json"
        lp = fu.lock_path(p)
        # 写入一个不存在的 PID
        lp.write_text(f"999999:{time.time()}")
        with fu.file_lock(p, timeout=2):
            assert lp.exists()
        # 成功获取说明 stale lock 被清理

    def test_stale_lock_cleaned_when_too_old(self, tmp_path):
        """锁文件过老时被清理。"""
        p = tmp_path / "data.json"
        lp = fu.lock_path(p)
        # 写入存活 PID 但创建时间很老（> 300s）
        import os

        old_ts = time.time() - 1000
        lp.write_text(f"{os.getpid()}:{old_ts}")
        with fu.file_lock(p, timeout=2):
            assert lp.exists()

    def test_corrupt_lock_content_cleaned(self, tmp_path):
        """锁文件内容损坏时被清理。"""
        p = tmp_path / "data.json"
        lp = fu.lock_path(p)
        lp.write_text("corrupt_content_no_colon")
        with fu.file_lock(p, timeout=2):
            assert lp.exists()

    def test_lock_with_single_pid_no_colon(self, tmp_path):
        """锁文件内容只有 PID（无冒号）时 _parse_lock_content 返回 (pid, 0.0)。"""
        p = tmp_path / "data.json"
        lp = fu.lock_path(p)
        # 纯数字 PID（无冒号）
        lp.write_text("999999")
        with fu.file_lock(p, timeout=2):
            assert lp.exists()


class TestFileLockConcurrency:
    def test_two_threads_serialize(self, tmp_path):
        """两个线程依次获取锁（互斥）。"""
        p = tmp_path / "data.json"
        order = []

        def _worker(name):
            with fu.file_lock(p, timeout=5):
                order.append(f"{name}-start")
                time.sleep(0.1)
                order.append(f"{name}-end")

        t1 = threading.Thread(target=_worker, args=("A",))
        t2 = threading.Thread(target=_worker, args=("B",))
        t1.start()
        time.sleep(0.02)
        t2.start()
        t1.join()
        t2.join()
        # 应完整执行 A 后再 B（或 B 后 A），不交错
        assert order in (
            ["A-start", "A-end", "B-start", "B-end"],
            ["B-start", "B-end", "A-start", "A-end"],
        )
