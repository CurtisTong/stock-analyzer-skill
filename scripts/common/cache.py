"""统一缓存管理。"""

import hashlib
import json
import logging
import os
import platform
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Windows 不支持 fcntl，用条件导入守护
_USE_FCNTL = platform.system() != "Windows"
if _USE_FCNTL:
    import fcntl

_DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache"
CACHE_DIR = Path(os.getenv("STOCK_CACHE_DIR", str(_DEFAULT_CACHE_DIR)))

# 惰性清理：每 N 次写入检查一次缓存大小
_WRITE_COUNTER = 0
_WRITE_LOCK = threading.Lock()
_CLEANUP_INTERVAL = 50  # 每 50 次写入检查一次
_MAX_CACHE_MB = 500  # 缓存上限


def _ensure_dir() -> None:
    CACHE_DIR.mkdir(exist_ok=True, mode=0o700)


def _validate_key(key: str) -> None:
    """校验缓存键安全性，拒绝路径遍历字符。"""
    if not key or "/" in key or "\\" in key or ".." in key:
        raise ValueError(f"非法缓存键（含路径遍历字符）: {key!r}")


def get(key: str, ttl_seconds: int) -> Optional[bytes]:
    """读取缓存，TTL 超时返回 None。"""
    _validate_key(key)
    _ensure_dir()
    f = CACHE_DIR / f"{key}.cache"
    if not f.exists():
        return None
    if time.time() - f.stat().st_mtime > ttl_seconds:
        f.unlink(missing_ok=True)
        return None
    return f.read_bytes()


def put(key: str, data: bytes) -> None:
    """写入缓存（原子写入：先写临时文件，再 rename）。

    非 Windows 平台使用 fcntl 文件锁防止多进程竞争。
    每 _CLEANUP_INTERVAL 次写入自动检查缓存大小，超限则清理。
    """
    _validate_key(key)
    global _WRITE_COUNTER
    need_cleanup = False
    with _WRITE_LOCK:
        _WRITE_COUNTER += 1
        if _WRITE_COUNTER >= _CLEANUP_INTERVAL:
            _WRITE_COUNTER = 0
            need_cleanup = True
    if need_cleanup:
        try:
            cleanup_by_size(max_size_mb=_MAX_CACHE_MB)
        except Exception as e:
            logger.debug("缓存清理失败: %s", e)  # 清理失败不影响写入
    _ensure_dir()
    f = CACHE_DIR / f"{key}.cache"
    fd, tmp_path = tempfile.mkstemp(dir=CACHE_DIR, suffix=".tmp")
    try:
        if _USE_FCNTL:
            fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, data)
        os.close(fd)
        fd = -1
        os.replace(tmp_path, f)
    except Exception as e:
        logger.debug("缓存写入失败 %s: %s", key, e)
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        Path(tmp_path).unlink(missing_ok=True)
        raise
    finally:
        # 确保异常路径也能清理 .tmp 残留（正常路径 tmp_path 已被 replace 走，unlink 无害）
        Path(tmp_path).unlink(missing_ok=True)


def set(key: str, data: bytes) -> None:
    """set 已更名为 put，保留向后兼容。"""
    import warnings

    warnings.warn("cache.set() 已更名为 cache.put()", DeprecationWarning, stacklevel=2)
    put(key, data)


def get_json(key: str, ttl_seconds: int) -> Any:
    """读取 JSON 缓存。"""
    raw = get(key, ttl_seconds)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def set_json(key: str, data: Any) -> None:
    """写入 JSON 缓存。"""
    put(key, json.dumps(data, ensure_ascii=False).encode())


def clear(prefix: str = "") -> None:
    """清除指定前缀或全部缓存。"""
    if not CACHE_DIR.exists():
        return
    for f in CACHE_DIR.glob("*.cache"):
        if not prefix or f.stem.startswith(prefix):
            f.unlink()


def cleanup(prefix: Optional[str] = None, max_age_seconds: int = 86400) -> int:
    """清理过期缓存。prefix 为空时清理所有过期文件。返回清理数量。"""
    _ensure_dir()
    cleaned = 0
    for f in CACHE_DIR.glob("*.cache"):
        if prefix and not f.name.startswith(prefix):
            continue
        if time.time() - f.stat().st_mtime > max_age_seconds:
            f.unlink(missing_ok=True)
            cleaned += 1
    return cleaned


# 数据格式版本号：当 API 返回字段格式变更时 bump 此值，自动失效旧缓存
_DATA_FORMAT_VERSION = "v2"


def cache_key(url: str) -> str:
    """用 URL 的 SHA256 生成缓存键（含数据格式版本）。"""
    versioned = f"{_DATA_FORMAT_VERSION}:{url}"
    return hashlib.sha256(versioned.encode()).hexdigest()[:32]


def cache_key_for_stock(prefix: str, code: str, **params: object) -> str:
    """生成股票相关的缓存键，支持按代码清除。
    格式: {prefix}_{code}_{param_hash}
    """
    param_str = "_".join(f"{k}={v}" for k, v in sorted(params.items()))
    versioned = f"{_DATA_FORMAT_VERSION}:{param_str}"
    param_hash = (
        hashlib.sha256(versioned.encode()).hexdigest()[:16] if param_str else ""
    )
    return f"{prefix}_{code}_{param_hash}".rstrip("_")


# ---------- 别名：带 cache_ 前缀的导出名（与 common.__init__.py 公开符号一致） ----------


def cache_get(key: str, ttl_seconds: int) -> Optional[bytes]:
    """get() 的别名，用于 `from common.cache import cache_get` 显式导入。"""
    return get(key, ttl_seconds)


def cache_set(key: str, data: bytes) -> None:
    """set() 的别名。"""
    put(key, data)


def cache_cleanup(prefix: Optional[str] = None, max_age_seconds: int = 86400) -> int:
    """cleanup() 的别名。"""
    return cleanup(prefix, max_age_seconds)


def cleanup_tmp_files() -> int:
    """清理缓存目录下的 *.tmp 残留文件（崩溃遗留）。返回清理数量。"""
    if not CACHE_DIR.exists():
        return 0
    cleaned = 0
    for f in CACHE_DIR.glob("*.tmp"):
        try:
            f.unlink()
            cleaned += 1
        except OSError:
            pass
    return cleaned


def cleanup_by_size(max_size_mb: int = 500, keep_newest: bool = True) -> int:
    """按缓存目录大小清理，保留最新文件。"""

    _ensure_dir()
    files = list(CACHE_DIR.glob("*.cache"))
    if not files:
        return 0

    file_stats = [(f, f.stat()) for f in files]
    total_size = sum(s.st_size for _, s in file_stats)
    max_size_bytes = max_size_mb * 1024 * 1024

    if total_size <= max_size_bytes:
        return 0

    file_stats.sort(key=lambda x: x[1].st_mtime, reverse=keep_newest)

    cleaned = 0
    current_size = total_size
    for f, s in file_stats:
        if current_size <= max_size_bytes:
            break
        f.unlink(missing_ok=True)
        current_size -= s.st_size
        cleaned += 1

    return cleaned


def get_cache_stats() -> dict[str, Any]:
    """获取缓存统计信息。

    Returns:
        {
            "total_files": int,
            "total_size_mb": float,
            "oldest_file": "ISO时间" | None,
            "newest_file": "ISO时间" | None
        }
    """
    _ensure_dir()

    files = list(CACHE_DIR.glob("*.cache"))
    if not files:
        return {
            "total_files": 0,
            "total_size_mb": 0.0,
            "oldest_file": None,
            "newest_file": None,
        }

    from datetime import datetime

    files_with_time = [(f, f.stat().st_mtime) for f in files]
    total_size = sum(f.stat().st_size for f, _ in files_with_time)

    return {
        "total_files": len(files),
        "total_size_mb": round(total_size / 1024 / 1024, 2),
        "oldest_file": datetime.fromtimestamp(
            min(t for _, t in files_with_time)
        ).isoformat(),
        "newest_file": datetime.fromtimestamp(
            max(t for _, t in files_with_time)
        ).isoformat(),
    }
