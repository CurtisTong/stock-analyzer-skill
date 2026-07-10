"""持仓模块共享的文件工具函数。

提供文件锁、原子写入、数据目录等公共功能，
避免 manager.py 和 trade_log.py 之间的代码重复。
"""

import json
import os
import tempfile
import threading
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
    """基于文件锁的并发保护机制（含 stale lock 检测 + PID 复用防御）。

    锁文件格式：`{pid}:{created_at_ts}`（ISO 紧凑格式或 epoch）。
    - PID 存活 + 锁创建时间在 _LOCK_STALE_SECONDS 内 → 锁有效，等待
    - PID 已死 或 锁创建时间超时 → 视为 stale lock，自动清理
    - 文件内容损坏 → 视为 stale lock，自动清理
    - PID 复用 + 旧锁未超时 → 仍视为有效（保守策略，避免误删活锁）

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
    # 先获取进程内线程锁，确保同进程多线程不会因共享 PID 而互相删除锁文件
    intra_lock = _get_intra_lock(str(lp))

    # 锁超过此秒数视为 stale（即便 PID 还活着）
    _LOCK_STALE_SECONDS = 300  # 5 分钟

    def _is_pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def _parse_lock_content(content: str):
        """解析锁文件内容，返回 (pid, created_ts) 或 (None, None)。"""
        try:
            parts = content.strip().split(":", 1)
            if len(parts) == 2:
                return int(parts[0]), float(parts[1])
            return int(parts[0]), 0.0
        except (ValueError, IndexError):
            return None, None

    def _try_clean_stale_lock() -> None:
        try:
            content = lp.read_text(encoding="utf-8").strip()
            old_pid, created_ts = _parse_lock_content(content)
            if old_pid is None:
                # 文件内容损坏：清掉
                lp.unlink(missing_ok=True)
                return
            # 三种 stale 情形：进程已死 / 内容超时 / 文件过老
            pid_dead = not _is_pid_alive(old_pid)
            too_old = (
                created_ts > 0
                and datetime.now().timestamp() - created_ts > _LOCK_STALE_SECONDS
            )
            if pid_dead or too_old:
                lp.unlink(missing_ok=True)
        except (ValueError, OSError):
            # 损坏文件：尝试清掉
            try:
                lp.unlink(missing_ok=True)
            except OSError:
                pass

    try:
        # 进程内线程锁优先（阻止同进程线程并发进入文件锁竞争）
        if not intra_lock.acquire(timeout=timeout):
            raise TimeoutError(f"获取进程内锁超时: {lp}")
        try:
            while True:
                try:
                    lock_fd = os.open(str(lp), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    # 写 pid:created_at 复合键，防御 PID 复用
                    payload = f"{os.getpid()}:{datetime.now().timestamp()}"
                    os.write(lock_fd, payload.encode())
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
                lp.unlink(missing_ok=True)
            except OSError:
                pass
    finally:
        intra_lock.release()


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
