"""静默降级异常与日志工具（v1.16.0 Batch 3 P1-2 治理）。

设计动机：项目历史上有 24 处 ``except Exception:`` 静默吞错，导致业务失败被
替换为默认值或 ``pass``——上游监控/告警完全失明。本模块提供：

1. ``SilentFallbackError`` — 显式标记"这是已知降级路径"的专用异常类。
2. ``log_silent_fallback()`` — 在所有吞错位置统一调用的日志函数，
   输出 ``logger.warning(..., extra={silent: True})``，便于运营 grep。
3. ``silent_fallback`` 装饰器 — 一键把"返回 None/默认值"的吞错变成可观测的
   静默降级，调用方一眼能看出这是有意为之而非 bug。

使用约定：
- LOW 风险位置（合理兜底：atomic write / browser fallback 等）：保留吞错。
- MEDIUM 风险：加 ``logger.warning("...", exc_info=False)`` 调用。
- HIGH 风险（universe_loader 黑名单、backtest/metrics 计算）：抛专用异常，
  由调用方显式决策降级或失败。
"""

import functools
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def log_silent_fallback(
    location: str,
    exception: Exception | None = None,
    *,
    default_value: Any = None,
    fallback_reason: str = "",
    extra_context: dict | None = None,
) -> None:
    """记录一处静默降级（P1-2 治理核心工具）。

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

    exc_repr = (
        f"{type(exception).__name__}: {exception}" if exception else "(no exception)"
    )
    logger.warning(
        "静默降级 @ %s | reason=%s | default=%s | exc=%s",
        location,
        fallback_reason,
        repr(default_value)[:100],
        exc_repr[:300],
        extra=extra,
    )


def silent_fallback(
    location: str,
    fallback_reason: str = "known safe degradation",
    default_value: Any = None,
):
    """装饰器：把吞错位置包成"显式静默降级"。

    用法::

        @silent_fallback("dcf.factor.compute_wacc", fallback_reason="WACC 输入不完整视为不可估值")
        def compute_wacc(...) -> float | None:
            ...

    装饰器捕获 ``Exception`` 子类，打 WARNING 日志后返回 ``default_value``。
    调用方一眼可看出"这是有意降级"，便于 grep 出来全面审视。
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:  # noqa: BLE001
                log_silent_fallback(
                    location=location,
                    exception=e,
                    default_value=default_value,
                    fallback_reason=fallback_reason,
                )
                return default_value

        return wrapper

    return decorator


__all__ = [
    "log_silent_fallback",
    "silent_fallback",
]
