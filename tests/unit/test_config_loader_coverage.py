"""config.loader 覆盖补充（v2.7 任务 B：coverage）。

覆盖 2026-08-13 基线缺口（config 62.8% → 目标 80%）：
- ConfigLoader.load: 缺失文件 / TTL 内直接返回 / TTL 过期走锁内双重检查
  / mtime 未变命中缓存 / mtime 变化重载
- get: 嵌套键路径 / 非 dict 中断 / 键缺失回退
- reload: 单文件 / 全量
- safe_get: 正常 / 异常回退
- get_scoring/get_limit/get_notification 便捷函数
"""

import tempfile
import time
from pathlib import Path

import pytest

# 配置目录可被 loader 内 class 常量指向的真实文件目录，直接复用
from config.loader import (
    ConfigLoader,
    get_limit_config,
    get_notification_config,
    get_scoring_config,
    reload_config,
    safe_get,
)

REAL_DIR = ConfigLoader._config_dir


@pytest.fixture
def clean_cache():
    ConfigLoader._cache.clear()
    ConfigLoader._cache_time.clear()
    yield
    ConfigLoader._cache.clear()
    ConfigLoader._cache_time.clear()


@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    """指向临时目录并生成一个小 YAML。"""
    d = tmp_path / "cfg"
    d.mkdir()
    f = d / "test.yaml"
    f.write_text("alpha: 1\nnested:\n  key: value\n", encoding="utf-8")
    monkeypatch.setattr(ConfigLoader, "_config_dir", d)
    return f


# ═══════════════════════════════════════════════════════════════
# load
# ═══════════════════════════════════════════════════════════════


class TestLoad:
    def test_missing_file_returns_empty(self, monkeypatch):
        monkeypatch.setattr(ConfigLoader, "_config_dir", Path(tempfile.gettempdir()))
        assert ConfigLoader.load("nonexistent.yaml") == {}

    def test_load_empty_yaml(self, temp_config):
        temp_config.write_text("", encoding="utf-8")
        assert ConfigLoader.load("test.yaml") == {}

    def test_load_basic(self, temp_config):
        cfg = ConfigLoader.load("test.yaml")
        assert cfg["alpha"] == 1
        assert cfg["nested"]["key"] == "value"

    def test_use_cache_false_reload(self, temp_config):
        # 关闭缓存时每次重读
        ConfigLoader.load("test.yaml")
        temp_config.write_text("alpha: 2\n", encoding="utf-8")
        assert ConfigLoader.load("test.yaml", use_cache=False)["alpha"] == 2

    def test_ttl_hit_returns_cached(self, temp_config, monkeypatch):
        # 先加载填充缓存
        ConfigLoader.load("test.yaml")
        # 篡改磁盘内容并抹掉 mtime 记录后的 stat 差异：
        temp_config.write_text("alpha: 99\n", encoding="utf-8")
        # 在 TTL 窗口内（未到 0.05s checkpoint）应直接返回缓存旧值
        cached = ConfigLoader.load("test.yaml")
        assert cached["alpha"] == 1

    def test_mtime_unchanged_returns_cache(self, temp_config):
        # TTL 过期但 mtime 未变 → 命中缓存（70-78 行锁内分支）
        ConfigLoader.load("test.yaml")
        ConfigLoader._cache_time["test.yaml"] = time.monotonic() - 1.0
        assert ConfigLoader.load("test.yaml")["alpha"] == 1

    def test_mtime_changed_reloads(self, temp_config):
        # mtime 更新 → 重读磁盘
        ConfigLoader.load("test.yaml")
        ConfigLoader._cache_time["test.yaml"] = time.monotonic() - 1.0
        import os

        os.utime(temp_config, (time.time() + 5, time.time() + 5))
        assert ConfigLoader.load("test.yaml")["alpha"] == 1

    def test_lock_inner_ttl_hit(self, temp_config):
        # 锁内双重检查命中（72 行）：外层 TTL 过期，进入锁时缓存时间已被其他线程刷新
        ConfigLoader.load("test.yaml")
        ConfigLoader._cache_time["test.yaml"] = time.monotonic() - 1.0

        class FakeLock:
            def __enter__(self):
                # 模拟并发线程在获得锁前刷新了 cache_time
                ConfigLoader._cache_time["test.yaml"] = time.monotonic()
                return self

            def __exit__(self, *exc):
                return False

        old_lock = ConfigLoader._lock
        ConfigLoader._lock = FakeLock()
        try:
            assert ConfigLoader.load("test.yaml")["alpha"] == 1
        finally:
            ConfigLoader._lock = old_lock


# ═══════════════════════════════════════════════════════════════
# get
# ═══════════════════════════════════════════════════════════════


class TestGet:
    def test_nested_key(self, temp_config):
        assert ConfigLoader.get("test.yaml", "nested.key") == "value"

    def test_missing_key_returns_default(self, temp_config):
        assert ConfigLoader.get("test.yaml", "nope") is None
        assert ConfigLoader.get("test.yaml", "nope", 42) == 42

    def test_non_dict_level_breaks(self, temp_config):
        # alpha 是 int，继续深入返回 default
        assert ConfigLoader.get("test.yaml", "alpha.x", 7) == 7

    def test_missing_file(self, monkeypatch):
        monkeypatch.setattr(ConfigLoader, "_config_dir", Path("/nonexistent"))
        assert ConfigLoader.get("nope.yaml", "a", 5) == 5


# ═══════════════════════════════════════════════════════════════
# reload
# ═══════════════════════════════════════════════════════════════


class TestReload:
    def test_reload_single(self, temp_config):
        ConfigLoader.load("test.yaml")
        assert "test.yaml" in ConfigLoader._cache
        reload_config("test.yaml")
        assert "test.yaml" not in ConfigLoader._cache

    def test_reload_all(self, temp_config):
        ConfigLoader.load("test.yaml")
        reload_config()
        assert ConfigLoader._cache == {}

    def test_reload_none_argument(self, temp_config):
        ConfigLoader.load("test.yaml")
        ConfigLoader.reload(None)
        assert ConfigLoader._cache == {}


# ═══════════════════════════════════════════════════════════════
# safe_get 便捷函数
# ═══════════════════════════════════════════════════════════════


class TestSafeGetAndHelpers:
    def test_safe_get_existing(self):
        # scoring.yaml 真实存在
        cfg = safe_get("scoring.yaml")
        assert isinstance(cfg, dict)
        assert "alignment_scores" in cfg
        assert safe_get("scoring.yaml", "alignment_scores.多头排列") == 20

    def test_safe_get_missing_file(self):
        assert safe_get("no_such_file.yaml") == {}

    def test_safe_get_exception_fallback(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("boom")

        monkeypatch.setattr(ConfigLoader, "load", classmethod(boom))
        assert safe_get("scoring.yaml", "a") is None

    def test_get_scoring_config(self):
        assert isinstance(get_scoring_config(), dict)
        assert get_scoring_config("alignment_scores.多头排列") == 20

    def test_get_limit_config(self):
        assert isinstance(get_limit_config(), dict)
        assert get_limit_config("nonexistent.path", 9) == 9

    def test_get_notification_config(self):
        cfg = get_notification_config()
        assert isinstance(cfg, dict)
        assert "channels" in cfg

    def test_get_notification_config_key(self):
        assert isinstance(get_notification_config("channels.bark.enabled"), bool)

    def test_safe_get_typeerror_fallback(self, monkeypatch):
        def boom(*a, **k):
            raise TypeError("bad type")

        monkeypatch.setattr(ConfigLoader, "load", classmethod(boom))
        assert safe_get("scoring.yaml") is None
        assert safe_get("scoring.yaml", "a") is None
        assert safe_get("scoring.yaml", "a", 1) == 1

    def test_safe_get_keyerror_fallback(self, monkeypatch):
        # KeyError → 走默认值（179 行场景）
        def boom(*a, **k):
            raise KeyError("missing")

        monkeypatch.setattr(ConfigLoader, "load", classmethod(boom))
        assert safe_get("what.yaml", "a", 99) == 99

    def test_safe_get_file_not_found(self, monkeypatch):
        # FileNotFoundError → 走默认值（177 行场景）
        def boom(*a, **k):
            raise FileNotFoundError

        monkeypatch.setattr(ConfigLoader, "load", classmethod(boom))
        assert safe_get("what.yaml", "a", 7) == 7

    def test_safe_get_keyerror_default(self, monkeypatch):
        # 缺 key 且带默认值 → 走 default（不抛异常分支）
        monkeypatch.setattr(ConfigLoader, "_config_dir", Path(tempfile.gettempdir()))
        assert safe_get("nope.yaml", "a", 99) == 99
