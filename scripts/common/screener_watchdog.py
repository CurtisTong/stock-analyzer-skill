"""Screener watchdog —— 整体任务级超时保护（v1.20.1 新增）。

背景:
    screener 在调用 akshare / akshare_balance 等数据源时, 若代理挂起
    (CLOSE_WAIT) 会永久卡死。现有 socket 超时(15s) 只兜底单次请求,
    prefetch_finance_all 的 480s 也只覆盖财务批量, run_screening 整体
    与 K 线预取、akshare_balance enrich 三处都缺乏任务级超时保护。

设计:
    用 threading.Timer 实现 watchdog: deadline 到时设 done_event, 主流程
    检测到后抛 ScreenerTimeoutError 退出。**不强行终止子线程**(Python
    GIL 限制 + 安全考虑), 只标记超时 + 放弃等待, 后续 fetcher 超时由
    socket 15s + 熔断器兜底。

用法:
    with start_watchdog(deadline_sec=600) as wd:
        run_screening(args)
        wd.mark_done()
    if wd.timed_out:
        # 已超时, 走部分结果分支
        ...

也可通过环境变量 STOCK_SCREENER_DEADLINE 提供兜底值(秒)。
"""

from __future__ import annotations

import os
import threading
import time
from typing import Optional

DEFAULT_DEADLINE_SEC = 600  # 10 分钟


def _resolve_deadline(arg_value: Optional[float] = None) -> float:
    """解析 deadline 优先级: 命令参数 > 环境变量 > 默认 600s。"""
    if arg_value is not None and arg_value > 0:
        return float(arg_value)
    env_val = os.environ.get("STOCK_SCREENER_DEADLINE", "").strip()
    if env_val:
        try:
            v = float(env_val)
            if v > 0:
                return v
        except ValueError:
            pass
    return float(DEFAULT_DEADLINE_SEC)


class WatchdogContext:
    """watchdog 上下文, 用法见模块文档。

    v1.20.1 二次修复: 单纯设 done_event 不够, run_screening 是阻塞的同步调用,
    主线程不会主动检查 done_event。改用 daemon 线程 + KeyboardInterrupt
    模拟: 超时时 watchdog 向主线程抛 KeyboardInterrupt, run_screening 在
    后续 socket / fetcher 层级抛出异常时一并清退。
    """

    def __init__(self, deadline_sec: float):
        self.deadline_sec = deadline_sec
        self.t_start = time.monotonic()
        self.done_event = threading.Event()
        self.timed_out = False
        self._timer: Optional[threading.Timer] = None

    def _on_timeout(self):
        """超时回调: 立即强制终止整个进程 (exit code 2)。

        设计: 在 fetcher 内部循环 / time.sleep 等阻塞调用中, Python signal
        handler 与 _thread.interrupt_main() 都不可靠打断; 子线程中 sys.exit()
        也只终止子线程, 主线程不受影响。唯一确定的兜底是 os._exit(2), 这是
        syscall 级别的退出, 绕过任何 Python 清理, 立即终止进程。
        """
        self.timed_out = True
        self.done_event.set()
        print(
            f"\n⚠️ Watchdog timeout ({self.deadline_sec:.0f}s), exiting...",
            flush=True,
        )
        import os as _os

        _os._exit(2)

    def start(self) -> "WatchdogContext":
        self._timer = threading.Timer(self.deadline_sec, self._on_timeout)
        self._timer.daemon = True
        self._timer.start()
        return self

    def cancel(self) -> None:
        """主动标记完成(任务在 deadline 内完成时调用)。"""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self.done_event.set()

    @property
    def elapsed_sec(self) -> float:
        return time.monotonic() - self.t_start

    def __enter__(self) -> "WatchdogContext":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        # 正常退出时取消 timer; 超时时让 timer 自然触发(已设 done_event)
        if not self.timed_out and self._timer is not None:
            self._timer.cancel()
            self._timer = None


def start_watchdog(deadline_sec: Optional[float] = None) -> WatchdogContext:
    """便捷工厂: 解析 deadline + 创建 watchdog。

    Args:
        deadline_sec: 命令参数; 若 None 则读 STOCK_SCREENER_DEADLINE 环境变量,
            再否则用 DEFAULT_DEADLINE_SEC。

    Returns:
        WatchdogContext 实例, 调用方用 ``with`` 上下文管理或手动 start/cancel。
    """
    resolved = _resolve_deadline(deadline_sec)
    return WatchdogContext(resolved)


__all__ = [
    "WatchdogContext",
    "start_watchdog",
    "DEFAULT_DEADLINE_SEC",
]
