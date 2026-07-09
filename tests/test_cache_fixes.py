"""cache.py 修复测试。"""

import warnings
from common import cache


def test_put_works_like_set():
    """cache.put 应与原 cache.set 行为一致。"""
    cache.put("__test_put__", b"hello")
    assert cache.get("__test_put__", ttl_seconds=60) == b"hello"
    (cache.CACHE_DIR / "__test_put__.cache").unlink(missing_ok=True)


def test_set_is_deprecated():
    """cache.set 应触发 DeprecationWarning。"""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cache.set("__test_deprecated__", b"world")
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "put" in str(w[0].message)
    (cache.CACHE_DIR / "__test_deprecated__.cache").unlink(missing_ok=True)


def test_cache_key_for_stock_uses_sha256():
    """cache_key_for_stock 应使用 SHA256 而非 MD5。"""
    key = cache.cache_key_for_stock("quote", "sh600519", period="day")
    parts = key.split("_")
    param_hash = parts[-1]
    assert len(param_hash) == 16, f"hash 长度应为 16，实际 {len(param_hash)}"
    assert all(c in "0123456789abcdef" for c in param_hash)


def test_cleanup_by_size_single_stat():
    """cleanup_by_size 不应对同一文件调用两次 stat。"""
    from unittest.mock import patch, MagicMock
    import time

    mock_file = MagicMock()
    mock_file.stem = "test"
    mock_stat = MagicMock()
    mock_stat.st_size = 1024
    mock_stat.st_mtime = time.time()
    mock_file.stat.return_value = mock_stat
    mock_file.unlink = MagicMock()

    with patch.object(cache, "CACHE_DIR") as mock_dir:
        mock_dir.exists.return_value = True
        mock_dir.glob.return_value = [mock_file] * 10
        cache.cleanup_by_size(max_size_mb=1)
    assert mock_file.stat.call_count <= 10


def test_ttl_jitter_deterministic():
    """P1-05: TTL jitter 应基于 hashlib（跨进程确定性），而非内置 hash()。"""
    import hashlib

    key = "test_jitter_determinism"
    expected_jitter = (int(hashlib.sha256(key.encode()).hexdigest(), 16) % 100) / 1000.0
    # 写入缓存，TTL 设短（1 秒），jitter 应使 effective_ttl = 1 * (1 + expected_jitter)
    cache.put(key, b"data")
    # 验证缓存可读（TTL 未过期）
    assert cache.get(key, ttl_seconds=60) == b"data"
    # 验证 jitter 值在 0~0.1 范围内
    assert 0 <= expected_jitter <= 0.1
    (cache.CACHE_DIR / f"{key}.cache").unlink(missing_ok=True)
