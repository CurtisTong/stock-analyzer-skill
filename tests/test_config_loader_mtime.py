"""ConfigLoader mtime 缓存失效测试。"""

import tempfile
import time
from pathlib import Path
from config.loader import ConfigLoader


def test_config_loader_auto_refresh_on_mtime_change():
    """配置文件修改后 load() 应自动刷新。"""
    config_dir = ConfigLoader._config_dir
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, dir=str(config_dir)
    )
    f.write("key: value1\n")
    f.flush()
    f.close()
    name = Path(f.name).name

    try:
        ConfigLoader._cache.pop(name, None)
        result1 = ConfigLoader.load(name, use_cache=True)
        assert result1["key"] == "value1"

        time.sleep(0.1)
        Path(f.name).write_text("key: value2\n", encoding="utf-8")

        result2 = ConfigLoader.load(name, use_cache=True)
        assert result2["key"] == "value2", f"期望 value2，实际 {result2.get('key')}"
    finally:
        Path(f.name).unlink(missing_ok=True)
        ConfigLoader._cache.pop(name, None)


def test_config_loader_cache_hit_on_unchanged():
    """文件未修改时应命中缓存。"""
    config_dir = ConfigLoader._config_dir
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, dir=str(config_dir)
    )
    f.write("key: cached\n")
    f.flush()
    f.close()
    name = Path(f.name).name

    try:
        ConfigLoader._cache.pop(name, None)
        r1 = ConfigLoader.load(name, use_cache=True)
        r2 = ConfigLoader.load(name, use_cache=True)
        assert r1 is r2, "同一文件应返回缓存对象"
    finally:
        Path(f.name).unlink(missing_ok=True)
        ConfigLoader._cache.pop(name, None)
