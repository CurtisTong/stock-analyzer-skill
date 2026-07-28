"""PortfolioManager 分析子模块（v1.17.0 god-class 拆分 P2-1 准备）。

从 ``scripts/portfolio/manager.py`` 抽取的纯只读分析方法：
- ``to_dict`` / ``summary``
- ``risk_summary``（基于 ``business.risk_metrics``）
- ``attribution_report``（基于 ``portfolio.brinson``）

设计原则（v1.16.0）：
- 每个函数接收一个 ``manager: PortfolioManager`` 参数
- 不持有状态、不修改 ``manager._data``
- 仅作为"组织性拆分"的第一步，便于 v1.17.0 完整抽离
- 现有 ``PortfolioManager.summary`` 等方法保留 thin wrapper 调用此处
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from portfolio.manager import PortfolioManager


def to_dict(manager: "PortfolioManager") -> dict:
    """返回完整数据浅副本。

    Args:
        manager: PortfolioManager 实例

    Returns:
        dict with positions/watchlist 为新 list，元素为共享引用
    """
    d = dict(manager._data)
    if "positions" in d:
        d["positions"] = list(d["positions"])
    if "watchlist" in d:
        d["watchlist"] = list(d["watchlist"])
    return d


def summary(manager: "PortfolioManager") -> str:
    """返回持仓摘要文本。

    Args:
        manager: PortfolioManager 实例

    Returns:
        文本摘要（持仓数 + 持仓明细 + 自选明细）
    """
    pos = manager.get_positions()
    watch = manager.get_watchlist()
    lines = [f"持仓 {len(pos)} 只，自选 {len(watch)} 只"]
    if pos:
        lines.append(
            "持仓: "
            + ", ".join(f"{p.get('name') or p['code']}({p['quantity']}股)" for p in pos)
        )
    if watch:
        lines.append("自选: " + ", ".join(w.get("name") or w["code"] for w in watch))
    return "\n".join(lines)


def risk_summary(
    manager: "PortfolioManager",
    quotes: dict | None = None,
    confidence: float = 0.95,
) -> str:
    """持仓组合 VaR 风险摘要（基于 ``business.risk_metrics``）。

    Args:
        manager: PortfolioManager 实例
        quotes: {code: current_price} 估值（未提供时用成本）
        confidence: 置信度（0.95 / 0.99）

    Returns:
        风险摘要文本
    """
    try:
        from business.risk_metrics import (
            compute_portfolio_var,
            format_var_report,
        )
    except ImportError:
        return "⚠️ business.risk_metrics 模块不可用，无法生成风险摘要"

    positions = manager.get_positions()
    if not positions:
        return "暂无持仓"

    # 默认估值：成本作为当前价（零 P&L）
    if not quotes:
        quotes = {p["code"]: p.get("cost", 0) for p in positions}

    result = compute_portfolio_var(positions, quotes, confidence=confidence)
    return format_var_report(result)


def attribution_report(
    manager: "PortfolioManager",
    quotes: dict | None = None,
    period: str = "1M",
) -> str:
    """组合 Brinson 归因报告（基于 ``portfolio.brinson``）。

    Args:
        manager: PortfolioManager 实例
        quotes: {code: current_price} 估值（必传，否则使用成本）
        period: 期间（仅显示用途）

    Returns:
        归因报告文本
    """
    try:
        from portfolio.brinson import brinson_from_holdings, format_brinson_report
    except ImportError:
        return "⚠️ brinson 模块不可用，无法生成归因报告"

    positions = manager.get_positions()
    if not positions:
        return "暂无持仓"

    if not quotes:
        quotes = {p["code"]: p.get("cost", 0) for p in positions}

    result = brinson_from_holdings(positions, quotes, period=period)
    return format_brinson_report(result)


__all__ = [
    "to_dict",
    "summary",
    "risk_summary",
    "attribution_report",
]
