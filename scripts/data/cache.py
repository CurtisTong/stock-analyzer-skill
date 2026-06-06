"""统一缓存管理。"""
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

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
    """写入缓存（原子写入：先写临时文件，再 rename）。"""
    _ensure_dir()
    f = CACHE_DIR / f"{key}.cache"
    fd, tmp_path = tempfile.mkstemp(dir=CACHE_DIR, suffix=".tmp")
    try:
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
