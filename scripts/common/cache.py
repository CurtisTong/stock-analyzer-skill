"""统一缓存管理。"""

import hashlib
import json
import logging
import os
import platform
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional
from common.exceptions.silent_fallback import log_silent_fallback

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
_MAX_CACHE_MB = 500  # 缓存上限（MB）

# P2 #8(4.1): YAML cache.max_size/max_age 的兜底默认值（data.config 不可用时）。
# max_size 语义 = 缓存文件数（与 YAML 注释一致），max_age 语义 = 文件存活秒数。
_FALLBACK_MAX_FILES = 1000
_FALLBACK_MAX_AGE_SECONDS = 604800

# P1-1(3.1): 跨进程互斥锁。key -> 进程内后备锁（Windows 无 fcntl 时用）。
_PER_KEY_LOCKS: dict[str, threading.Lock] = {}
_PER_KEY_LOCKS_LOCK = threading.Lock()


def _ensure_dir() -> None:
    CACHE_DIR.mkdir(exist_ok=True, mode=0o700)


def _lock_path(key: str) -> Path:
    """P1-1(3.1): 按 key 返回**固定**的锁文件路径。

    修复前 flock 加在 mkstemp 创建的唯一临时 inode 上，各进程锁的是不同文件，
    跨进程互斥从未生效。锁文件本身以 ``.lock`` 结尾，不属于 ``*.cache``，
    因此不会被 clear()/cleanup()/cleanup_by_size() 误删；也不要在清理逻辑里
    主动删除它——删除正在被别的进程持有的锁文件会破坏互斥（TOCTOU）。
    """
    return CACHE_DIR / f"{key}.lock"


@contextmanager
def _key_lock(key: str) -> Iterator[None]:
    """P1-1(3.1): 按 key 加跨进程排他锁（非 Windows 用 fcntl.flock）。

    同一 key 的所有写入者锁同一个稳定 inode，锁内完成检查/写入/os.replace；
    退出时显式解锁。Windows 无 fcntl，退化为进程内 per-key Lock。
    """
    if not _USE_FCNTL:
        with _PER_KEY_LOCKS_LOCK:
            lock = _PER_KEY_LOCKS.setdefault(key, threading.Lock())
        with lock:
            yield
        return
    _ensure_dir()
    with open(_lock_path(key), "a+b") as lock_file:
        fd = lock_file.fileno()
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)


def _effective_cache_limits() -> tuple[int, int]:
    """P2 #8(4.1): 读取 YAML cache.max_size/max_age，让死配置真正生效。

    惰性导入 data.config 避免 common.cache ↔ data.__init__ 循环依赖。
    """
    try:
        from data.config import get_config

        cfg = get_config()
        return (
            int(getattr(cfg, "cache_max_size", _FALLBACK_MAX_FILES)),
            int(getattr(cfg, "cache_max_age", _FALLBACK_MAX_AGE_SECONDS)),
        )
    except Exception as e:
        log_silent_fallback("cache._effective_cache_limits", e)
        logger.debug("读取缓存容量配置失败，使用默认值: %s", e)
        return _FALLBACK_MAX_FILES, _FALLBACK_MAX_AGE_SECONDS


def _validate_key(key: str) -> None:
    """校验缓存键安全性，拒绝路径遍历字符。"""
    if not key or "/" in key or "\\" in key or ".." in key:
        raise ValueError(f"非法缓存键（含路径遍历字符）: {key!r}")


def get(key: str, ttl_seconds: int) -> Optional[bytes]:
    """读取缓存，TTL 超时返回 None。

    v2.4.0: TTL 加抖动（+0~10%），防止大量缓存同时过期（雪崩）。
    """
    _validate_key(key)
    _ensure_dir()
    f = CACHE_DIR / f"{key}.cache"
    if not f.exists():
        return None
    # TTL 抖动：基于 key 的确定性偏移（0~10%），避免雪崩
    # 用 hashlib.sha256 替代内置 hash()，后者受 PYTHONHASHSEED 随机化影响，
    # 跨进程/重启抖动值不一致，与"确定性偏移"目标矛盾
    jitter = (int(hashlib.sha256(key.encode()).hexdigest(), 16) % 100) / 1000.0
    effective_ttl = ttl_seconds * (1 + jitter)
    if time.time() - f.stat().st_mtime > effective_ttl:
        f.unlink(missing_ok=True)
        return None
    return f.read_bytes()


def put(key: str, data: bytes) -> None:
    """写入缓存（原子写入：先写临时文件，再 rename）。

    P1-1(3.1): 修复"伪锁"——锁不再加在 mkstemp 的唯一临时 inode 上，
    而是按 key 锁固定 ``.lock`` 文件，并把「检查 / 写入 / replace」全部放进
    临界区，跨进程写入同一 key 才真正互斥。

    P2 #8(4.1): 周期性清理同时消费 YAML cache.max_size（文件数）与
    cache.max_age（秒）；清理只处理 ``*.cache``，不会碰 ``*.lock``。
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
            max_files, max_age = _effective_cache_limits()
            cleanup_by_size(max_size_mb=_MAX_CACHE_MB)
            cleanup_by_count(max_files=max_files)
            cleanup(max_age_seconds=max_age)
        except Exception as e:
            log_silent_fallback("cache.put", e)
            logger.debug("缓存清理失败: %s", e)  # 清理失败不影响写入
    _ensure_dir()
    f = CACHE_DIR / f"{key}.cache"
    with _key_lock(key):
        # P1-1: 锁内完成临时文件写入 + replace；锁文件是稳定 inode，跨进程生效
        fd, tmp_path = tempfile.mkstemp(dir=CACHE_DIR, suffix=".tmp")
        try:
            os.write(fd, data)
            os.replace(tmp_path, f)
            os.close(fd)
            fd = -1
        except Exception as e:
            log_silent_fallback("cache.put", e)
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
    """清除指定前缀或全部缓存。

    P1-1: 仅匹配 ``*.cache``，固定的 ``*.lock`` 互斥文件不在清理范围内。
    """
    if not CACHE_DIR.exists():
        return
    for f in CACHE_DIR.glob("*.cache"):
        if not prefix or f.stem.startswith(prefix):
            # P2-H3: missing_ok 避免并发清理时文件已被删除抛 FileNotFoundError
            f.unlink(missing_ok=True)


def cleanup(prefix: Optional[str] = None, max_age_seconds: int = 86400) -> int:
    """清理过期缓存。prefix 为空时清理所有过期文件。返回清理数量。

    P1-1: 只匹配 ``*.cache``，``*.lock`` 固定锁文件永不清理（删锁会破坏互斥）。
    P2 #8: max_age_seconds 可由 YAML cache.max_age 经 put() 周期清理注入。
    """
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
# v3 (2026-07-21): 财务数据 FinanceRecord Optional[float]=None 化 + 删 7 字段
#   -> 旧缓存以 0.0 写入，新代码读出为 None，可能引发 NoneType 错误
# v4 (2026-08-05): get_quote/get_kline 缓存内容从 to_dict()（已归一化）改为
#   fetcher 原始 dict（未归一化），修复缓存命中时双重归一化 bug
#   （total_cap 1696.94 亿 -> 1.7e-5 亿 / amount 1.72e9 元 -> 1.72e13 元）
_DATA_FORMAT_VERSION = "v4"


def cache_key(url: str) -> str:
    """用 URL 的 SHA256 生成缓存键（含数据格式版本）。"""
    versioned = f"{_DATA_FORMAT_VERSION}:{url}"
    return hashlib.sha256(versioned.encode()).hexdigest()[:32]


def cache_key_for_stock(prefix: str, code: str, **params: object) -> str:
    """生成股票相关的缓存键，支持按代码清除。
    格式: {prefix}_{code}_{param_hash}

    版本号始终编入 key（即使无 params），确保 bump _DATA_FORMAT_VERSION 时
    无 params 的缓存（如 quote）也能自动失效。无 params 时用纯版本哈希，
    保持 key 可读性且仍含 code 段以支持按代码清除。
    """
    param_str = "_".join(f"{k}={v}" for k, v in sorted(params.items()))
    versioned = f"{_DATA_FORMAT_VERSION}:{param_str}"
    param_hash = hashlib.sha256(versioned.encode()).hexdigest()[:16]
    return f"{prefix}_{code}_{param_hash}"


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


def cleanup_by_count(max_files: int = 1000, keep_newest: bool = True) -> int:
    """P2 #8(4.1): 按缓存**文件数**清理，消费 YAML cache.max_size。

    只处理 ``*.cache``；``*.lock`` 是跨进程互斥的固定 inode，永不删除。
    """
    _ensure_dir()
    files = list(CACHE_DIR.glob("*.cache"))
    if len(files) <= max_files:
        return 0
    files.sort(key=lambda f: f.stat().st_mtime, reverse=keep_newest)
    cleaned = 0
    for f in files[max_files:]:
        f.unlink(missing_ok=True)
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

    files_with_stat = [(f, f.stat()) for f in files]
    files_with_time = [(f, s.st_mtime) for f, s in files_with_stat]
    total_size = sum(s.st_size for _, s in files_with_stat)

    return {
        "total_files": len(files),
        "total_size_mb": round(total_size / 1024 / 1024, 2),
        "oldest_file": datetime.fromtimestamp(min(t for _, t in files_with_time)).isoformat(),
        "newest_file": datetime.fromtimestamp(max(t for _, t in files_with_time)).isoformat(),
    }
