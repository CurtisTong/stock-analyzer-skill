"""持仓模块共享的文件工具函数。

提供文件锁、原子写入、数据目录等公共功能，
避免 manager.py 和 trade_log.py 之间的代码重复。
"""

import fcntl
import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# 进程内互斥锁：file_lock 基于文件 PID 无法区分同进程多线程
# （共享 PID），需额外用 threading.Lock 保证同进程内线程互斥。
_intra_locks: dict[str, threading.Lock] = {}
_intra_locks_guard = threading.Lock()


def _get_intra_lock(path: str) -> threading.Lock:
    """获取路径对应的进程内线程锁（惰性创建）。"""
    with _intra_locks_guard:
        if path not in _intra_locks:
            _intra_locks[path] = threading.Lock()
        return _intra_locks[path]


def data_dir() -> Path:
    """返回 scripts/data 目录。"""
    return Path(__file__).resolve().parent.parent / "data"


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def lock_path(path: Path) -> Path:
    """返回与数据文件对应的锁文件路径。"""
    return path.parent / f".{path.stem}.lock"


@contextmanager
def file_lock(path: Path, timeout: float = 10.0):
    """基于 fcntl.flock 的跨进程文件锁（review P2 修复 TOCTOU + stale 误判）。

    旧实现用 O_EXCL 抢锁 + 按内容删除"stale"锁文件，存在两处结构性缺陷：
    1. TOCTOU：B 在 A 检查完与 unlink 之间新建的锁会被 A 删除，双进程同时
       进入临界区并互相覆盖写；
    2. 5 分钟 stale 判定会把仍活着的长事务锁误判为过期。

    flock 由内核绑定在 fd 上：进程退出（含崩溃）自动释放；锁文件保留不
    删除，因此"检查后删除别人新锁"的窗口从根本上消失。锁文件内容仅作诊断
    （pid:时间戳），不再作为是否持有锁的判据。

    Args:
        path: 数据文件路径
        timeout: 获取锁超时时间（秒）

    Raises:
        TimeoutError: 获取锁超时
        OSError: 锁文件操作失败
    """
    lp = lock_path(path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    # 同进程多线程仍用 threading.Lock 串行化（flock 语义依平台/实现而异）
    intra_lock = _get_intra_lock(str(lp))
    lock_fd = None
    start_time = time.time()

    if not intra_lock.acquire(timeout=timeout):
        raise TimeoutError(f"获取进程内锁超时: {lp}")
    try:
        while True:
            if lock_fd is None:
                lock_fd = os.open(str(lp), os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                # 锁被其他进程持有：保留同一个 fd 重试，绝不删除锁文件
                if time.time() - start_time > timeout:
                    os.close(lock_fd)
                    lock_fd = None
                    raise TimeoutError(f"获取锁超时: {lp}")
                time.sleep(0.05)
        # 持锁期间写诊断信息；不 unlink 锁文件（TOCTOU 修复的核心）
        try:
            os.ftruncate(lock_fd, 0)
            os.lseek(lock_fd, 0, os.SEEK_SET)
            os.write(lock_fd, f"{os.getpid()}:{time.time()}".encode())
        except OSError:
            pass
        yield
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(lock_fd)
            except OSError:
                pass
        intra_lock.release()


def raw_write(path: Path, data: dict) -> None:
    """底层 JSON 写入（调用方需已持锁）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            # review P3：fsync 后再 replace，断电不会留下空/截断的 portfolio.json
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))
        # 目录项也尽量持久化（某些文件系统不支持目录 fsync，best effort）
        try:
            dir_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write(path: Path, data: dict) -> None:
    """原子写入 JSON 文件（加锁保护）。"""
    with file_lock(path):
        raw_write(path, data)
