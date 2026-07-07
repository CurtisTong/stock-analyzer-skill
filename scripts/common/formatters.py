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

# 向后兼容：从新模块 re-export
from common.glossary import (  # noqa: F401
    GLOSSARY,
    format_glossary,
    add_glossary,
    auto_detect_terms,
)
from common.exporters import (  # noqa: F401
    RISK_DISCLAIMER,
    add_risk_disclaimer,
    export_to_csv,
    export_analysis_to_csv,
)


def format_output(
    conclusion: str,
    data_time: Optional[str] = None,
    sources: Optional[List[str]] = None,
    failed_sources: Optional[List[str]] = None,
    ttl_sec: Optional[int] = None,
    body: Optional[str] = None,
    *,
    emoji: str = "🎯",
    confidence: Optional[float] = None,
) -> str:
    """生成统一格式的 skill 输出。

    v2.4.0 新增 confidence 参数：当数据源部分降级时，
    低于 60 的置信度会在结论行后显示 ⚠️ 置信度标识。
    """
    lines = []
    lines.append(f"{emoji} {conclusion}")

    # v2.4.0: 降级置信度标识
    if confidence is not None and confidence < 60:
        lines.append(f"⚠️ 数据置信度: {confidence:.0f}/100（部分数据源降级）")

    lines.append("")
    if body:
        lines.append(body.rstrip())
        lines.append("")

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
    """仅生成一句话结论行（不带尾行）。"""
    return f"{emoji} {conclusion}"


def format_footer(
    data_time: Optional[str] = None,
    sources: Optional[List[str]] = None,
    failed_sources: Optional[List[str]] = None,
    ttl_sec: Optional[int] = None,
) -> str:
    """仅生成尾行（数据源 + 时间戳）。"""
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


def collect_source_evidence(
    fetcher_results: dict[str, object | None],
) -> tuple[list[str], list[str]]:
    """从 fetcher 结果中收集数据源证据。"""
    sources = []
    failed = []
    for name, result in fetcher_results.items():
        if result is not None:
            sources.append(name)
        else:
            failed.append(name)
    return sources, failed


def format_with_enhancements(
    text: str,
    terms: Optional[List[str]] = None,
    auto_glossary: bool = False,
    risk_disclaimer: bool = True,
) -> str:
    """为输出添加增强功能（术语解释 + 风险提示）。"""
    result = text
    if auto_glossary and not terms:
        terms = auto_detect_terms(text)
    if terms:
        result = add_glossary(result, terms)
    if risk_disclaimer:
        result = add_risk_disclaimer(result)
    return result
