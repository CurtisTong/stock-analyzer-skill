"""ConfigLoader 并发安全测试（P2-23）。

验证当前 TTL + 双重检查锁实现在多线程并发 load() 时的正确性：
- 不丢失数据（每个线程都能获得有效配置）
- 不崩溃（无竞态导致的异常）
- 缓存一致性（并发后缓存条目存在且内容正确）

这些测试作为行为基线，供未来简化重构（TODO v2.0）后回归验证。
"""

import tempfile
import threading
from pathlib import Path

from config.loader import ConfigLoader


def test_concurrent_load_no_crash_no_data_loss():
    """P2-23: 多线程并发 load 同一文件不应崩溃或丢数据。"""
    config_dir = ConfigLoader._config_dir
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, dir=str(config_dir)
    )
    f.write("concurrent_key: concurrent_value\n")
    f.flush()
    f.close()
    name = Path(f.name).name

    results = []
    errors = []
    barrier = threading.Barrier(8)

    def worker():
        try:
            barrier.wait(timeout=5)
            for _ in range(20):
                r = ConfigLoader.load(name, use_cache=True)
                results.append(r)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]

    try:
        ConfigLoader._cache.pop(name, None)
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
    finally:
        Path(f.name).unlink(missing_ok=True)
        ConfigLoader._cache.pop(name, None)

    assert not errors, f"并发 load 抛出异常: {errors}"
    assert len(results) == 8 * 20, f"结果数量不符: {len(results)}"
    for r in results:
        assert r["concurrent_key"] == "concurrent_value"


def test_concurrent_load_cache_consistency():
    """P2-23: 并发 load 后缓存条目应存在且内容正确。"""
    config_dir = ConfigLoader._config_dir
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, dir=str(config_dir)
    )
    f.write("consistency_key: 42\n")
    f.flush()
    f.close()
    name = Path(f.name).name

    barrier = threading.Barrier(4)

    def worker():
        barrier.wait(timeout=5)
        ConfigLoader.load(name, use_cache=True)

    threads = [threading.Thread(target=worker) for _ in range(4)]

    try:
        ConfigLoader._cache.pop(name, None)
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # 并发后缓存应存在
        assert name in ConfigLoader._cache
        cached_mtime, cached_data = ConfigLoader._cache[name]
        assert cached_data["consistency_key"] == 42
    finally:
        Path(f.name).unlink(missing_ok=True)
        ConfigLoader._cache.pop(name, None)


def test_concurrent_load_different_files():
    """P2-23: 多线程加载不同文件互不干扰。"""
    config_dir = ConfigLoader._config_dir
    files = []
    names = []

    for i in range(4):
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, dir=str(config_dir)
        )
        f.write(f"file_idx: {i}\n")
        f.flush()
        f.close()
        files.append(Path(f.name))
        names.append(Path(f.name).name)

    errors = []

    def worker(idx):
        try:
            for _ in range(15):
                r = ConfigLoader.load(names[idx], use_cache=True)
                assert r["file_idx"] == idx, f"文件 {idx} 数据错乱"
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]

    try:
        for name in names:
            ConfigLoader._cache.pop(name, None)
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
    finally:
        for fp in files:
            fp.unlink(missing_ok=True)
        for name in names:
            ConfigLoader._cache.pop(name, None)

    assert not errors, f"并发加载不同文件出错: {errors}"
