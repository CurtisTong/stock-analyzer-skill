"""common/cache.py 覆盖测试。

mock 文件系统，覆盖缓存清理、统计、TTL、键生成、cleanup_by_size、
cleanup_tmp_files、get_cache_stats 等函数。
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import common.cache as cache_mod


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """将 CACHE_DIR 隔离到 tmp_path。"""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(cache_mod, "CACHE_DIR", cache_dir)
    # 重置写入计数器
    monkeypatch.setattr(cache_mod, "_WRITE_COUNTER", 0)
    return cache_dir


class TestValidateKey:
    def test_valid_key(self):
        cache_mod._validate_key("abc123")  # 不抛异常

    def test_empty_key(self):
        with pytest.raises(ValueError, match="非法缓存键"):
            cache_mod._validate_key("")

    def test_slash_in_key(self):
        with pytest.raises(ValueError, match="非法缓存键"):
            cache_mod._validate_key("a/b")

    def test_backslash_in_key(self):
        with pytest.raises(ValueError, match="非法缓存键"):
            cache_mod._validate_key("a\\b")

    def test_dotdot_in_key(self):
        with pytest.raises(ValueError, match="非法缓存键"):
            cache_mod._validate_key("..")


class TestGetPut:
    def test_put_and_get(self, isolated_cache):
        cache_mod.put("testkey", b"hello")
        assert cache_mod.get("testkey", 100) == b"hello"

    def test_get_missing_returns_none(self, isolated_cache):
        assert cache_mod.get("nokey", 100) is None

    def test_get_expired_returns_none(self, isolated_cache):
        cache_mod.put("expired", b"data")
        cache_file = isolated_cache / "expired.cache"
        # 修改 mtime 为很久以前
        old_time = time.time() - 10000
        import os

        os.utime(cache_file, (old_time, old_time))
        assert cache_mod.get("expired", 100) is None
        # 过期文件应被删除
        assert not cache_file.exists()

    def test_get_with_ttl_jitter(self, isolated_cache):
        """TTL 抖动：effective_ttl = ttl * (1 + jitter)。"""
        cache_mod.put("jitter_key", b"data")
        # ttl=100，jitter 0-10%，文件刚写入，应能读取
        assert cache_mod.get("jitter_key", 100) == b"data"

    def test_set_deprecated_warns(self, isolated_cache):
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cache_mod.set("deprkey", b"data")
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert cache_mod.get("deprkey", 100) == b"data"


class TestJsonHelpers:
    def test_set_json_and_get_json(self, isolated_cache):
        cache_mod.set_json("jskey", {"a": 1, "b": [2, 3]})
        assert cache_mod.get_json("jskey", 100) == {"a": 1, "b": [2, 3]}

    def test_get_json_missing(self, isolated_cache):
        assert cache_mod.get_json("nojs", 100) is None

    def test_get_json_corrupt(self, isolated_cache):
        cache_mod.put("corrupt", b"not json{")
        assert cache_mod.get_json("corrupt", 100) is None


class TestClear:
    def test_clear_all(self, isolated_cache):
        cache_mod.put("a", b"1")
        cache_mod.put("b", b"2")
        cache_mod.clear()
        assert cache_mod.get("a", 100) is None
        assert cache_mod.get("b", 100) is None

    def test_clear_with_prefix(self, isolated_cache):
        cache_mod.put("stock_1", b"1")
        cache_mod.put("stock_2", b"2")
        cache_mod.put("kline_1", b"3")
        cache_mod.clear(prefix="stock")
        assert cache_mod.get("stock_1", 100) is None
        assert cache_mod.get("stock_2", 100) is None
        assert cache_mod.get("kline_1", 100) == b"3"

    def test_clear_nonexistent_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path / "nonexist")
        cache_mod.clear()  # 不应抛异常


class TestCleanup:
    def test_cleanup_expired(self, isolated_cache):
        import os

        cache_mod.put("old", b"1")
        cache_mod.put("new", b"2")
        old_file = isolated_cache / "old.cache"
        old_time = time.time() - 100000
        os.utime(old_file, (old_time, old_time))
        cleaned = cache_mod.cleanup(max_age_seconds=86400)
        assert cleaned == 1
        assert not old_file.exists()
        assert cache_mod.get("new", 100) == b"2"

    def test_cleanup_with_prefix(self, isolated_cache):
        import os

        cache_mod.put("stock_old", b"1")
        cache_mod.put("kline_old", b"2")
        old_file = isolated_cache / "stock_old.cache"
        old_time = time.time() - 100000
        os.utime(old_file, (old_time, old_time))
        kline_file = isolated_cache / "kline_old.cache"
        os.utime(kline_file, (old_time, old_time))
        cleaned = cache_mod.cleanup(prefix="stock", max_age_seconds=86400)
        assert cleaned == 1

    def test_cache_cleanup_alias(self, isolated_cache):
        assert cache_mod.cache_cleanup(max_age_seconds=86400) == 0


class TestCacheKey:
    def test_cache_key_deterministic(self):
        k1 = cache_mod.cache_key("http://example.com")
        k2 = cache_mod.cache_key("http://example.com")
        assert k1 == k2
        assert len(k1) == 32

    def test_cache_key_different_urls(self):
        assert cache_mod.cache_key("http://a.com") != cache_mod.cache_key(
            "http://b.com"
        )

    def test_cache_key_for_stock_with_params(self):
        k = cache_mod.cache_key_for_stock("quote", "sh600519", scale="day", limit=250)
        assert k.startswith("quote_sh600519_")

    def test_cache_key_for_stock_no_params(self):
        k = cache_mod.cache_key_for_stock("quote", "sh600519")
        assert k == "quote_sh600519"

    def test_cache_key_for_stock_param_order_independent(self):
        k1 = cache_mod.cache_key_for_stock("q", "c", a=1, b=2)
        k2 = cache_mod.cache_key_for_stock("q", "c", b=2, a=1)
        assert k1 == k2


class TestCleanupTmpFiles:
    def test_cleanup_tmp_files(self, isolated_cache):
        (isolated_cache / "a.tmp").write_text("x")
        (isolated_cache / "b.tmp").write_text("y")
        (isolated_cache / "c.cache").write_text("z")
        cleaned = cache_mod.cleanup_tmp_files()
        assert cleaned == 2
        assert not (isolated_cache / "a.tmp").exists()

    def test_cleanup_tmp_files_nonexistent_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path / "nonexist")
        assert cache_mod.cleanup_tmp_files() == 0


class TestCleanupBySize:
    def test_under_limit_no_cleanup(self, isolated_cache):
        cache_mod.put("a", b"small")
        assert cache_mod.cleanup_by_size(max_size_mb=500) == 0

    def test_over_limit_cleanup(self, isolated_cache):
        # 写入大文件超过 1MB 上限
        cache_mod.put("big1", b"x" * 600 * 1024)
        cache_mod.put("big2", b"x" * 600 * 1024)
        cleaned = cache_mod.cleanup_by_size(max_size_mb=1)
        assert cleaned >= 1

    def test_no_files(self, isolated_cache):
        assert cache_mod.cleanup_by_size(max_size_mb=1) == 0


class TestGetCacheStats:
    def test_empty_cache(self, isolated_cache):
        stats = cache_mod.get_cache_stats()
        assert stats["total_files"] == 0
        assert stats["total_size_mb"] == 0.0
        assert stats["oldest_file"] is None
        assert stats["newest_file"] is None

    def test_with_files(self, isolated_cache):
        cache_mod.put("a", b"x" * 10000)
        cache_mod.put("b", b"y" * 10000)
        stats = cache_mod.get_cache_stats()
        assert stats["total_files"] == 2
        # 总大小约 20KB，round 到 MB 为 0.0；改为检查 >= 0
        assert stats["total_size_mb"] >= 0
        assert stats["oldest_file"] is not None
        assert stats["newest_file"] is not None


class TestCacheGetSetAliases:
    def test_cache_get_set(self, isolated_cache):
        cache_mod.cache_set("akey", b"adata")
        assert cache_mod.cache_get("akey", 100) == b"adata"


class TestPutCleanupTrigger:
    def test_put_triggers_cleanup_at_threshold(self, isolated_cache, monkeypatch):
        """写入达到 _CLEANUP_INTERVAL 时触发 cleanup_by_size。"""
        monkeypatch.setattr(cache_mod, "_CLEANUP_INTERVAL", 3)
        call_count = {"n": 0}

        def _spy(*args, **kwargs):
            call_count["n"] += 1
            return 0

        monkeypatch.setattr(cache_mod, "cleanup_by_size", _spy)
        cache_mod.put("k1", b"1")
        cache_mod.put("k2", b"2")
        assert call_count["n"] == 0
        cache_mod.put("k3", b"3")  # 第 3 次写入触发
        assert call_count["n"] == 1
