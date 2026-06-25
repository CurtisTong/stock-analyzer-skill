"""持仓模块共享的文件工具函数。

提供文件锁、原子写入、数据目录等公共功能，
避免 manager.py 和 trade_log.py 之间的代码重复。
"""

import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


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
    """基于文件锁的并发保护机制（含 stale lock 检测）。

    锁文件中写入 PID，启动时检查持有锁的进程是否存活。
    若进程已退出则清理残留锁文件，避免永久阻塞。

    Args:
        path: 数据文件路径
        timeout: 获取锁超时时间（秒）

    Raises:
        TimeoutError: 获取锁超时
        OSError: 锁文件操作失败
    """
    lp = lock_path(path)
    lock_fd = None
    start_time = datetime.now().timestamp()

    def _is_pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def _try_clean_stale_lock() -> None:
        try:
            content = lp.read_text(encoding="utf-8").strip()
            old_pid = int(content)
            if not _is_pid_alive(old_pid):
                lp.unlink(missing_ok=True)
        except (ValueError, OSError):
            pass

    try:
        while True:
            try:
                lock_fd = os.open(str(lp), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(lock_fd, str(os.getpid()).encode())
                break
            except FileExistsError:
                _try_clean_stale_lock()
                if datetime.now().timestamp() - start_time > timeout:
                    raise TimeoutError(f"获取锁超时: {lp}")
                import time

                time.sleep(0.05)
        yield
    finally:
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except OSError:
                pass
        try:
            os.unlink(str(lp))
        except OSError:
            pass


def raw_write(path: Path, data: dict) -> None:
    """底层 JSON 写入（调用方需已持锁）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(path))
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
