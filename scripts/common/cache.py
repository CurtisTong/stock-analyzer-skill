"""统一缓存管理。"""
import hashlib
import json
import os
import platform
import tempfile
import time
from pathlib import Path
from typing import Optional

# Windows 不支持 fcntl，用条件导入守护
_USE_FCNTL = platform.system() != "Windows"
if _USE_FCNTL:
    import fcntl

_DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache"
CACHE_DIR = Path(os.getenv("STOCK_CACHE_DIR", str(_DEFAULT_CACHE_DIR)))


def _ensure_dir():
    CACHE_DIR.mkdir(exist_ok=True)


def get(key: str, ttl_seconds: int) -> Optional[bytes]:
    """读取缓存，TTL 超时返回 None。"""
    _ensure_dir()
    f = CACHE_DIR / f"{key}.cache"
    if not f.exists():
        return None
    if time.time() - f.stat().st_mtime > ttl_seconds:
        f.unlink(missing_ok=True)
        return None
    return f.read_bytes()


def set(key: str, data: bytes):
    """写入缓存（原子写入：先写临时文件，再 rename）。

    非 Windows 平台使用 fcntl 文件锁防止多进程竞争。
    """
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
    except Exception:
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


def get_json(key: str, ttl_seconds: int):
    """读取 JSON 缓存。"""
    raw = get(key, ttl_seconds)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def set_json(key: str, data):
    """写入 JSON 缓存。"""
    set(key, json.dumps(data, ensure_ascii=False).encode())


def clear(prefix: str = ""):
    """清除指定前缀或全部缓存。"""
    if not CACHE_DIR.exists():
        return
    for f in CACHE_DIR.glob("*.cache"):
        if not prefix or f.stem.startswith(prefix):
            f.unlink()


def cleanup(prefix: str = None, max_age_seconds: int = 86400):
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


def cache_key(url: str) -> str:
    """用 URL 的 SHA256 生成缓存键。"""
    return hashlib.sha256(url.encode()).hexdigest()[:32]


def cache_key_for_stock(prefix: str, code: str, **params) -> str:
    """生成股票相关的缓存键，支持按代码清除。
    格式: {prefix}_{code}_{param_hash}
    """
    param_str = "_".join(f"{k}={v}" for k, v in sorted(params.items()))
    param_hash = hashlib.md5(param_str.encode()).hexdigest()[:8] if param_str else ""
    return f"{prefix}_{code}_{param_hash}".rstrip("_")


# ---------- 别名：带 cache_ 前缀的导出名（与 common.__init__.py 公开符号一致） ----------

def cache_get(key: str, ttl_seconds: int) -> Optional[bytes]:
    """get() 的别名，用于 `from common.cache import cache_get` 显式导入。"""
    return get(key, ttl_seconds)


def cache_set(key: str, data: bytes) -> None:
    """set() 的别名。"""
    set(key, data)


def cache_cleanup(prefix: str = None, max_age_seconds: int = 86400) -> int:
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
    """按缓存目录大小清理，保留最新文件。

    Args:
        max_size_mb: 缓存目录最大允许大小（MB）
        keep_newest: True=保留最新文件，False=保留最旧文件

    Returns:
        清理的文件数量
    """
    import shutil

    _ensure_dir()

    # 计算当前总大小
    files = list(CACHE_DIR.glob("*.cache"))
    if not files:
        return 0

    total_size = sum(f.stat().st_size for f in files)
    max_size_bytes = max_size_mb * 1024 * 1024

    if total_size <= max_size_bytes:
        return 0

    # 按修改时间排序
    if keep_newest:
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    else:
        files.sort(key=lambda f: f.stat().st_mtime)

    # 从最旧的开始删除，直到大小合适
    cleaned = 0
    current_size = total_size
    for f in files:
        if current_size <= max_size_bytes:
            break
        file_size = f.stat().st_size
        f.unlink(missing_ok=True)
        current_size -= file_size
        cleaned += 1

    return cleaned


def get_cache_stats() -> dict:
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
        "oldest_file": datetime.fromtimestamp(min(t for _, t in files_with_time)).isoformat(),
        "newest_file": datetime.fromtimestamp(max(t for _, t in files_with_time)).isoformat(),
    }
