"""PortfolioManager 调仓建议子模块（v1.17.0 god-class 拆分 准备）。

从 ``scripts/portfolio/manager.py`` 抽取的 ``advisory_rebalance`` 方法。
纯只读操作，不修改 ``manager._data``。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from portfolio.manager import PortfolioManager


def advisory_rebalance(
    manager: "PortfolioManager",
    target_ratio: float = 1.0,
    quotes: dict | None = None,
) -> list:
    """(#12) 宏观仓位控制的调仓建议（纯只读，不修改 portfolio）。

    根据 MacroState.position_ratio 生成减仓建议，将每个持仓压缩至 target_ratio。

    Args:
        manager: PortfolioManager 实例
        target_ratio: 目标仓位比例（0.0~1.0，来自 MacroState.position_ratio）
        quotes: {code: current_price} 市价估值（缺省用成本价）

    Returns:
        调仓建议列表，每个元素:
        {
            "code": str,
            "name": str,
            "action": "reduce",
            "current_value": float,
            "target_value": float,
            "reduce_value": float,
            "reason": str,
        }
        GREEN（target_ratio=1.0）时返回空列表。
    """
    positions = manager.get_positions()
    if not positions or target_ratio >= 1.0:
        return []

    suggestions = []
    for pos in positions:
        code = pos.get("code", "")
        name = pos.get("name", "")
        cost = float(pos.get("cost", 0))
        quantity = float(pos.get("quantity", 0))

        # 市价估值：优先用 quotes，否则用成本价
        if quotes and code in quotes:
            current_price = float(quotes[code])
        else:
            current_price = cost

        current_value = current_price * quantity
        target_value = current_value * target_ratio
        reduce_value = current_value - target_value

        if reduce_value > 0:
            suggestions.append(
                {
                    "code": code,
                    "name": name,
                    "action": "reduce",
                    "current_value": round(current_value, 2),
                    "target_value": round(target_value, 2),
                    "reduce_value": round(reduce_value, 2),
                    "reason": f"宏观{int(target_ratio * 100)}%仓位控制",
                }
            )

    return suggestions


__all__ = ["advisory_rebalance"]
