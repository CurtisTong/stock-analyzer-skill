"""静默降级异常与日志工具（v1.16.0 Batch 3 治理）。

设计动机：项目历史上有 24 处 ``except Exception:`` 静默吞错，导致业务失败被
替换为默认值或 ``pass``--上游监控/告警完全失明。本模块提供：

1. ``SilentFallbackError`` - 显式标记"这是已知降级路径"的专用异常类。
2. ``log_silent_fallback()`` - 在所有吞错位置统一调用的日志函数，
   输出 ``logger.warning(..., extra={silent: True})``，便于运营 grep。

使用约定：
- LOW 风险位置（合理兜底：atomic write / browser fallback 等）：保留吞错。
- MEDIUM 风险：加 ``logger.warning("...", exc_info=False)`` 调用。
- HIGH 风险（universe_loader 黑名单、backtest/metrics 计算）：抛专用异常，
  由调用方显式决策降级或失败。
"""

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


# 已知可选依赖：缺失属于正常环境差异，不是故障（全市场 5000 只会触发 5000 次）
_OPTIONAL_DEPS = frozenset(
    {"akshare", "pandas", "yfinance", "efinance", "tushare", "pytdx", "baostock", "numpy", "yaml"}
)

# P2 #7(4.1): 两级去重——
# 1) 可选依赖缺失：永久去重（确属环境差异，一旦提示过就不必再提）；
# 2) 真实故障（网络/接口改版）：**完整 location 纳入 key + 时间窗限速**，
#    窗口过后再次 warning。旧实现按 (模块, 异常类型) 永久去重，一次早期瞬时
#    错误会永久占掉告警名额，后续同模块真实故障全部降 debug 且永不再报。
_SEEN: set[tuple[str, str]] = set()                    # 可选依赖：永久去重键
_LAST_WARN: dict[tuple[str, str], float] = {}          # 真实故障：(location, 异常类型) -> 上次 warning 时刻
_SEEN_LOCK = threading.Lock()
_NON_OPTIONAL_WINDOW_SECONDS = 60.0  # 真实故障告警时间窗（秒）


def _missing_optional_dep(exception: Exception | None) -> str | None:
    """若异常是"已知可选依赖未安装"，返回依赖名；否则 None。"""
    if exception is None:
        return None
    name = getattr(exception, "name", None) or ""
    dep = str(name).split(".")[0]
    if dep in _OPTIONAL_DEPS:
        return dep
    msg = str(exception)
    for candidate in _OPTIONAL_DEPS:
        if f"No module named '{candidate}'" in msg:
            return candidate
    return None


def _mark_seen(key: tuple[str, str]) -> bool:
    """可选依赖缺失：首次出现返回 True 并登记；重复返回 False。线程安全。"""
    with _SEEN_LOCK:
        if key in _SEEN:
            return False
        _SEEN.add(key)
        return True


def _rate_limited(key: tuple[str, str], now: float) -> bool:
    """P2 #7(4.1): 真实故障时间窗限速。

    窗口内重复返回 True（调用方降级为 debug）；窗口首次或已过期返回 False
    并刷新时间戳（调用方输出 warning）。线程安全。
    """
    with _SEEN_LOCK:
        last = _LAST_WARN.get(key)
        if last is not None and now - last < _NON_OPTIONAL_WINDOW_SECONDS:
            return True
        _LAST_WARN[key] = now
        return False


def reset_dedupe() -> None:
    """清空去重状态（仅测试用）。"""
    with _SEEN_LOCK:
        _SEEN.clear()
        _LAST_WARN.clear()


def log_silent_fallback(
    location: str,
    exception: Exception | None = None,
    *,
    default_value: Any = None,
    fallback_reason: str = "",
    extra_context: dict | None = None,
) -> None:
    """记录一处静默降级（治理核心工具）。

    Args:
        location: 业务位置（如 ``"universe_loader.load_blacklist"``）
        exception: 被吞掉的异常（用于栈首行）
        default_value: 降级后使用的默认值（仅日志中记录，便于排查）
        fallback_reason: 为什么这是可接受的降级（如"配置缺失使用零权重"
        extra_context: 额外上下文（如涉及到的 code/file 等）
    """
    extra = {
        "silent": True,
        "location": location,
        "default_value": repr(default_value)[:200],
        "fallback_reason": fallback_reason,
    }
    if extra_context:
        extra.update(extra_context)

    exc_repr = f"{type(exception).__name__}: {exception}" if exception else "(no exception)"

    # 去重 + 分级（2026-11-20；2026-11-21 review P2 #7 修订）：
    # 全市场取数时每只股票都会触发同一个可选依赖缺失，warning 每行输出会刷爆
    # stderr（实测 1 万+ 字节）并淹没真降级。规则：
    # - 已知可选依赖缺失：debug 级，单进程内同一 (module, 异常类型) **永久**只输出一次；
    # - 其他失败（网络/接口改版）：首次 warning，同一 (完整 location, 异常类型)
    #   在时间窗内只报一次并降 debug，窗口过后可再次 warning（真实复发不再被永久静默）。
    module = location.rsplit(".", 1)[0] if "." in location else location
    optional_dep = _missing_optional_dep(exception)

    if optional_dep:
        dedupe_key = (module, f"{type(exception).__name__}:{optional_dep}")
        first_time = _mark_seen(dedupe_key)
        extra["dedupe_key"] = f"{module}:{dedupe_key[1]}"
        if not first_time:
            return
        logger.debug(
            "静默降级（可选依赖缺失，仅首次提示）@ %s | reason=%s | 缺 %s | exc=%s",
            location,
            fallback_reason,
            optional_dep,
            exc_repr[:200],
            extra=extra,
        )
        return

    # P2 #7: 真实故障用「完整 location + 异常类型」做 key，并按时间窗限速；
    # 不再用 (module, 异常类型) 永久去重，避免同模块其它位置的真实故障被吞。
    real_key = (location, type(exception).__name__)
    extra["dedupe_key"] = f"{real_key[0]}:{real_key[1]}"
    if _rate_limited(real_key, time.time()):
        logger.debug(
            "静默降级（同因已提示过）@ %s | reason=%s | exc=%s",
            location,
            fallback_reason,
            exc_repr[:200],
            extra=extra,
        )
        return

    logger.warning(
        "静默降级 @ %s | reason=%s | default=%s | exc=%s",
        location,
        fallback_reason,
        repr(default_value)[:100],
        exc_repr[:300],
        extra=extra,
    )


__all__ = [
    "log_silent_fallback",
]
