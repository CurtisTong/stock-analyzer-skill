"""统一输出格式化工具。

为 12 个 skill 提供一致的输出结构：
  - 首行：一句话结论（🎯 / 🔴 / 🟢 / 🟡 emoji 前缀）
  - 尾行：数据时间戳 + 数据源 + 失败源

用法示例::

    from common.formatters import format_output
    result = format_output(
        conclusion="可分批介入，回踩 1620 加仓",
        data_time="2026-06-15 14:30",
        sources=["腾讯行情", "东方财富财务"],
        failed_sources=["新浪K线"],
        ttl_sec=900,
    )
    print(result)
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional


def format_output(
    conclusion: str,
    data_time: Optional[str] = None,
    sources: Optional[List[str]] = None,
    failed_sources: Optional[List[str]] = None,
    ttl_sec: Optional[int] = None,
    body: Optional[str] = None,
    *,
    emoji: str = "🎯",
) -> str:
    """生成统一格式的 skill 输出。

    Args:
        conclusion: 一句话结论（必填）
        data_time: 数据时间戳，如 "2026-06-15 14:30"
        sources: 使用的数据源列表
        failed_sources: 失败的数据源列表
        ttl_sec: 数据 TTL（秒），用于提示"数据是 X 秒前的"
        body: 中间详细内容（五层分析、专家辩论等）
        emoji: 结论前缀 emoji，默认 🎯

    Returns:
        格式化的完整输出字符串
    """
    lines = []

    # ── 首行：一句话结论 ──
    lines.append(f"{emoji} {conclusion}")
    lines.append("")

    # ── 中间：详细内容 ──
    if body:
        lines.append(body.rstrip())
        lines.append("")

    # ── 尾行：数据源与时间戳 ──
    footer_parts = []

    if data_time:
        footer_parts.append(f"数据时间戳: {data_time}")

    if sources:
        footer_parts.append(f"数据源: {', '.join(sources)}")

    if failed_sources:
        footer_parts.append(f"⚠️ 失败源: {', '.join(failed_sources)}")

    if ttl_sec is not None:
        footer_parts.append(f"数据 TTL: {ttl_sec}s")

    if footer_parts:
        lines.append("─" * 40)
        lines.append("📊 " + " | ".join(footer_parts))

    return "\n".join(lines)


def format_conclusion(conclusion: str, emoji: str = "🎯") -> str:
    """仅生成一句话结论行（不带尾行）。

    适合 quick 模式等轻量输出场景。
    """
    return f"{emoji} {conclusion}"


def format_footer(
    data_time: Optional[str] = None,
    sources: Optional[List[str]] = None,
    failed_sources: Optional[List[str]] = None,
    ttl_sec: Optional[int] = None,
) -> str:
    """仅生成尾行（数据源 + 时间戳）。

    适合需要手动拼接 body 的场景。
    """
    footer_parts = []
    if data_time:
        footer_parts.append(f"数据时间戳: {data_time}")
    if sources:
        footer_parts.append(f"数据源: {', '.join(sources)}")
    if failed_sources:
        footer_parts.append(f"⚠️ 失败源: {', '.join(failed_sources)}")
    if ttl_sec is not None:
        footer_parts.append(f"数据 TTL: {ttl_sec}s")

    if not footer_parts:
        return ""
    return "─" * 40 + "\n📊 " + " | ".join(footer_parts)


def now_str() -> str:
    """返回当前时间的格式化字符串。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def collect_source_evidence(fetcher_results: dict[str, object | None]) -> tuple[list[str], list[str]]:
    """从 fetcher 结果中收集数据源证据。

    Args:
        fetcher_results: {fetcher_name: result_or_None} 字典

    Returns:
        (成功源列表, 失败源列表)
    """
    sources = []
    failed = []
    for name, result in fetcher_results.items():
        if result is not None:
            sources.append(name)
        else:
            failed.append(name)
    return sources, failed
