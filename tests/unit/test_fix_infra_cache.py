"""2026-11-21 code review 基础设施修复回归：缓存伪锁 + 死配置消费。

- P1-1(§3.1 #1)：flock 从唯一临时 inode 改为按 key 的固定 .lock 文件；
- P2 #8(§4.1)：YAML cache.max_size/max_age 由 common.cache 真正消费。
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import common.cache as cache


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path, monkeypatch):
    """每个用例使用独立缓存目录，避免污染真实 .cache。"""
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "_WRITE_COUNTER", 0)
    return tmp_path


class TestP1FixedKeyLock:
    """P1-1：跨进程互斥必须锁在按 key 固定的 inode 上。"""

    def test_lock_path_is_stable_and_suffixed_lock(self, _isolated_cache_dir):
        assert cache._lock_path("abc") == _isolated_cache_dir / "abc.lock"
        assert cache._lock_path("abc") == cache._lock_path("abc")

    def test_lock_file_survives_all_cleanup_paths(self, _isolated_cache_dir):
        """锁文件不能被 clear/cleanup/cleanup_by_count/cleanup_tmp_files 误删。"""
        cache.put("abc", b"value")
        assert (_isolated_cache_dir / "abc.cache").exists()
        lock_file = _isolated_cache_dir / "abc.lock"
        assert lock_file.exists(), "put 应创建固定 .lock 文件"

        cache.clear()
        cache.cleanup(max_age_seconds=0)
        cache.cleanup_tmp_files()
        cache.cleanup_by_count(max_files=0)

        assert not (_isolated_cache_dir / "abc.cache").exists()
        assert lock_file.exists(), "清理逻辑不得删除正在使用的锁文件"

    def test_same_key_lock_blocks_other_thread(self, _isolated_cache_dir):
        """同 key 的两把锁互斥（flock 在不同 open 的文件描述间生效）。"""
        holder_started = threading.Event()

        def holder():
            with cache._key_lock("shared"):
                holder_started.set()
                time.sleep(0.4)

        t = threading.Thread(target=holder)
        t.start()
        assert holder_started.wait(2)
        start = time.time()
        with cache._key_lock("shared"):
            waited = time.time() - start
        t.join(timeout=2)
        assert waited >= 0.25, f"同 key 应串行，实际等待 {waited:.3f}s"

    def test_cross_process_lock_blocks(self, _isolated_cache_dir):
        """真正的跨进程互斥：子进程获取同 key 的锁必须等父进程释放。"""
        scripts_dir = Path(cache.__file__).resolve().parent.parent
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(scripts_dir), env.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        child = (
            "import sys, time\n"
            "from pathlib import Path\n"
            "import common.cache as c\n"
            "c.CACHE_DIR = Path(sys.argv[1])\n"
            "t = time.time()\n"
            "with c._key_lock('cross'):\n"
            "    print(f'{time.time() - t:.3f}')\n"
        )

        holder_started = threading.Event()

        def holder():
            with cache._key_lock("cross"):
                holder_started.set()
                time.sleep(0.5)

        t = threading.Thread(target=holder)
        t.start()
        assert holder_started.wait(2)
        start = time.time()
        result = subprocess.run(
            [sys.executable, "-c", child, str(_isolated_cache_dir)],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        elapsed = time.time() - start
        t.join(timeout=2)
        assert result.returncode == 0, result.stderr
        assert elapsed >= 0.3, f"子进程应被父进程的同 key 锁阻塞，实际 {elapsed:.3f}s"

    def test_put_is_atomic_with_lock_held(self, _isolated_cache_dir):
        """锁内写完再 replace，读侧不会看到半截内容。"""
        cache.put("k", b"payload")
        assert cache.get("k", 60) == b"payload"
        # 临时文件已被 replace，不应残留
        assert list(_isolated_cache_dir.glob("*.tmp")) == []


class TestP2CacheConfigConsumer:
    """P2 #8：YAML cache.max_size/max_age 不再是死配置。"""

    def test_limits_read_from_data_config(self, monkeypatch):
        from data import config as dc

        monkeypatch.setattr(
            dc,
            "get_config",
            lambda: SimpleNamespace(cache_max_size=7, cache_max_age=11),
        )
        assert cache._effective_cache_limits() == (7, 11)

    def test_limits_fall_back_when_config_unavailable(self, monkeypatch):
        from data import config as dc

        def boom():
            raise RuntimeError("config down")

        monkeypatch.setattr(dc, "get_config", boom)
        assert cache._effective_cache_limits() == (
            cache._FALLBACK_MAX_FILES,
            cache._FALLBACK_MAX_AGE_SECONDS,
        )

    def test_cleanup_by_count_enforces_max_files(self, _isolated_cache_dir):
        for i in range(5):
            cache.put(f"k{i}", f"v{i}".encode())
        assert len(list(_isolated_cache_dir.glob("*.cache"))) == 5
        removed = cache.cleanup_by_count(max_files=2)
        assert removed == 3
        assert len(list(_isolated_cache_dir.glob("*.cache"))) == 2
