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
from typing import Any

logger = logging.getLogger(__name__)


# 已知可选依赖：缺失属于正常环境差异，不是故障（全市场 5000 只会触发 5000 次）
_OPTIONAL_DEPS = frozenset(
    {"akshare", "pandas", "yfinance", "efinance", "tushare", "pytdx", "baostock", "numpy", "yaml"}
)

# 单进程内已提示过的 (module, 异常类型) 组合
_SEEN: set[tuple[str, str]] = set()
_SEEN_LOCK = threading.Lock()


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
    """首次出现返回 True 并登记；重复返回 False。线程安全。"""
    with _SEEN_LOCK:
        if key in _SEEN:
            return False
        _SEEN.add(key)
        return True


def reset_dedupe() -> None:
    """清空去重状态（仅测试用）。"""
    with _SEEN_LOCK:
        _SEEN.clear()


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

    # 去重 + 分级（2026-11-20）：
    # 全市场取数时每只股票都会触发同一个可选依赖缺失，warning 每行输出会刷爆
    # stderr（实测 1 万+ 字节）并淹没真降级。规则：
    # - 已知可选依赖缺失：debug 级，单进程内同一 (module, 异常类型) 只输出一次；
    # - 其他失败（网络/接口改版）：首次按原级别 warning，后续同因只给 debug；
    # - 去重键 = (module, 异常类型:可选依赖名)，module 取 location 的模块前缀。
    module = location.rsplit(".", 1)[0] if "." in location else location
    optional_dep = _missing_optional_dep(exception)
    dedupe_key = (module, f"{type(exception).__name__}:{optional_dep}" if optional_dep else type(exception).__name__)
    first_time = _mark_seen(dedupe_key)
    extra["dedupe_key"] = f"{module}:{dedupe_key[1]}"

    if optional_dep:
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

    if not first_time:
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
