"""统一缓存管理。"""
import json
import time
from pathlib import Path
from typing import Optional

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache"


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
    """写入缓存。"""
    _ensure_dir()
    f = CACHE_DIR / f"{key}.cache"
    f.write_bytes(data)


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
