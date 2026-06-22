"""缓存并发安全测试。"""

import os
import threading
from pathlib import Path
from unittest.mock import patch

import pytest


# 使用临时目录隔离测试缓存
@pytest.fixture
def isolated_cache(tmp_path):
    """将 CACHE_DIR 指向临时目录，测试结束后自动清理。"""
    with patch("scripts.common.cache.CACHE_DIR", tmp_path):
        # 同时 patch common 模块中 re-export 的引用
        with patch("scripts.common.CACHE_DIR", tmp_path):
            yield tmp_path


def test_concurrent_writes_same_key(isolated_cache):
    """10 个线程同时写同一 key，最终值是某一线程的有效写入。"""
    from scripts.common.cache import put, get

    key = "concurrent_test_key"
    num_threads = 10
    barrier = threading.Barrier(num_threads)
    results = [f"thread_{i}".encode() for i in range(num_threads)]

    def writer(value):
        barrier.wait()  # 所有线程同时出发
        put(key, value)

    threads = [
        threading.Thread(target=writer, args=(results[i],)) for i in range(num_threads)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = get(key, ttl_seconds=3600)
    assert final is not None, "get(key) 应返回非 None"
    assert final in results, f"最终值 {final!r} 应是某一线程写入的有效值之一"


def test_no_tmp_files_remaining(isolated_cache):
    """并发写入后不应有 .tmp 残留文件。"""
    from scripts.common.cache import put

    key = "tmp_cleanup_test"
    num_threads = 10
    barrier = threading.Barrier(num_threads)

    def writer(i):
        barrier.wait()
        put(key, f"data_{i}".encode())

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    tmp_files = list(isolated_cache.glob("*.tmp"))
    assert tmp_files == [], f"不应有 .tmp 残留，但发现: {tmp_files}"


def test_cleanup_tmp_files(isolated_cache):
    """cleanup_tmp_files 应清理 .tmp 残留。"""
    from scripts.common.cache import cleanup_tmp_files

    # 手动创建几个 .tmp 文件
    for i in range(3):
        (isolated_cache / f"stale_{i}.tmp").write_bytes(b"crash-remnant")

    # 创建一个正常 .cache 文件不应被清理
    (isolated_cache / "normal.cache").write_bytes(b"ok")

    cleaned = cleanup_tmp_files()
    assert cleaned == 3
    assert list(isolated_cache.glob("*.tmp")) == []
    assert (isolated_cache / "normal.cache").exists()


def test_cleanup_tmp_files_empty_dir(isolated_cache):
    """空目录调用 cleanup_tmp_files 应返回 0。"""
    from scripts.common.cache import cleanup_tmp_files

    assert cleanup_tmp_files() == 0
