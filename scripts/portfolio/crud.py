"""PortfolioManager 持仓/自选 CRUD 子模块（P2-P1 god-class 拆分）。

从 ``scripts/portfolio/manager.py`` 抽取的全部写操作方法：
- ``add_position`` / ``reduce_position`` / ``remove_position`` / ``update_position``
- ``tag_position`` / ``untag_position`` 以及自选 ``add_watch`` / ``remove_watch``
- 内部辅助 ``_record_trade_log`` / ``_position_cost``（仅 CRUD 使用）

设计原则（沿用 v1.16.0 analytics 拆分约定）：
- 每个函数接收一个 ``manager: PortfolioManager`` 参数
- 通过 ``manager.atomic_update`` / ``manager._data`` / ``manager._push_oplog``
  等既有接口操作，不含独立状态
- ``PortfolioManager`` 对应方法保留为 thin wrapper 一行委托
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from common.validators import normalize_code
from portfolio._file_utils import today as _today

if TYPE_CHECKING:
    from portfolio.manager import PortfolioManager

logger = logging.getLogger(__name__)


def _record_trade_log(
    manager: "PortfolioManager",
    code: str,
    name: str,
    cost: float,
    quantity: int,
    reason: str = "manual",
    sell_price: float = None,
) -> None:
    """记录交易日志（异常隔离，不影响持仓操作）。"""
    try:
        from portfolio.trade_log import TradeLog

        tl = TradeLog()
        tl.record(
            code=code,
            name=name,
            cost=cost,
            quantity=quantity,
            sell_price=sell_price or 0,
            reason=reason,
        )
    except Exception as e:
        logger.debug("交易日志记录失败: %s", e)  # 交易日志失败不阻塞持仓操作


def _position_cost(manager: "PortfolioManager", code: str) -> Optional[float]:
    """返回持仓当前成本价（P1-03 变更对比用），无持仓返回 None。"""
    code = normalize_code(code)
    for p in manager._data.get("positions", []):
        if p["code"].lower() == code:
            return p.get("cost")
    return None


def add_position(
    manager: "PortfolioManager",
    code: str,
    name: str,
    cost: float,
    quantity: int,
    buy_date: str = "",
    tags: list = None,
    auto_save: bool = True,
    cost_source: str = "user_input",
) -> dict:
    """添加持仓。如果已存在则加仓（加权平均成本）。

    P1-03a: cost_source 记录成本来源（user_input / screenshot / calculated），
    加仓产生加权平均成本时自动置为 calculated，保留可追溯性。
    """
    code = normalize_code(code)
    cost_before = _position_cost(manager, code)
    manager._push_oplog(
        "add_position", code=code, cost_before=cost_before, cost_source=cost_source
    )
    result_holder: dict[str, Any] = {}

    def _apply(data: dict) -> dict:
        positions = data.setdefault("positions", [])
        existing = None
        for p in positions:
            if p["code"].lower() == code:
                existing = p
                break
        if existing:
            # 加仓：计算加权平均成本
            old_qty = existing.get("quantity", 0)
            old_cost = existing.get("cost", 0)
            new_qty = old_qty + quantity
            if new_qty > 0:
                new_cost = (old_cost * old_qty + cost * quantity) / new_qty
            else:
                new_cost = cost
            existing["cost"] = round(new_cost, 3)
            existing["quantity"] = new_qty
            # 加权平均成本由计算得出，成本来源标记为 calculated
            existing["cost_source"] = "calculated"
            if name and not existing.get("name"):
                existing["name"] = name
            if buy_date:
                existing["buy_date"] = buy_date
            if tags:
                existing["tags"] = list(set(existing.get("tags", []) + tags))
            result_holder["r"] = existing
        else:
            new_pos = {
                "code": code,
                "name": name or "",
                "cost": round(cost, 3),
                "quantity": quantity,
                "buy_date": buy_date or _today(),
                "tags": tags or [],
                "cost_source": cost_source,
            }
            positions.append(new_pos)
            result_holder["r"] = new_pos
        return data

    if auto_save:
        manager.atomic_update(_apply)
    else:
        _apply(manager._data)
    r = result_holder["r"]
    if r is not None:
        manager._oplog_backfill(
            "add_position",
            cost_after=r.get("cost"),
            cost_source=r.get("cost_source"),
        )
    return r


def reduce_position(
    manager: "PortfolioManager",
    code: str,
    quantity: int,
    auto_save: bool = True,
    sell_price: float = None,
) -> Optional[dict]:
    """减仓。返回减仓后的持仓信息，如果全部卖出则移除并记录交易日志。"""
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    code = normalize_code(code)
    manager._push_oplog("reduce_position", code=code)
    result_holder: dict[str, Any] = {"r": None, "cleared": False, "pos": None}

    def _apply(data: dict) -> dict:
        positions = data.get("positions", [])
        for i, p in enumerate(positions):
            if p["code"].lower() == code:
                # 超量减仓 → 全部清仓
                actual_qty = min(quantity, p["quantity"])
                p["quantity"] -= actual_qty
                if p["quantity"] <= 0:
                    result_holder["cleared"] = True
                    result_holder["pos"] = p
                    result_holder["actual_qty"] = actual_qty
                    positions.pop(i)
                    return data
                # 部分减仓
                result_holder["r"] = p
                result_holder["pos"] = p
                result_holder["actual_qty"] = actual_qty
                return data
        return data

    if auto_save:
        manager.atomic_update(_apply)
    else:
        _apply(manager._data)

    # 交易日志在锁外记录（独立文件，失败不阻塞持仓操作）
    pos = result_holder.get("pos")
    actual_qty = result_holder.get("actual_qty", 0)
    if pos is not None:
        if result_holder.get("cleared"):
            _record_trade_log(
                manager,
                code,
                pos.get("name", ""),
                pos.get("cost", 0),
                actual_qty,
                reason="reduce_to_zero",
                sell_price=sell_price,
            )
        elif sell_price:
            _record_trade_log(
                manager,
                code,
                pos.get("name", ""),
                pos.get("cost", 0),
                actual_qty,
                reason="partial_reduce",
                sell_price=sell_price,
            )
    return result_holder["r"]


def remove_position(
    manager: "PortfolioManager", code: str, auto_save: bool = True
) -> bool:
    """清仓（移除持仓）并记录交易日志。"""
    code = normalize_code(code)
    manager._push_oplog("remove_position", code=code)
    holder: dict[str, Any] = {"found": False, "pos": None}

    def _apply(data: dict) -> dict:
        positions = data.get("positions", [])
        for i, p in enumerate(positions):
            if p["code"].lower() == code:
                holder["found"] = True
                holder["pos"] = p
                positions.pop(i)
                return data
        return data

    if auto_save:
        manager.atomic_update(_apply)
    else:
        _apply(manager._data)

    if holder["found"] and holder["pos"] is not None:
        p = holder["pos"]
        _record_trade_log(
            manager,
            code,
            p.get("name", ""),
            p.get("cost", 0),
            p.get("quantity", 0),
            reason="manual",
        )
    return holder["found"]


def update_position(
    manager: "PortfolioManager", code: str, auto_save: bool = True, **kwargs
) -> Optional[dict]:
    """更新持仓字段（cost, quantity, name, buy_date, tags, cost_source）。

    P1-03a/c: cost 变更时记录 cost_before/cost_after 到 oplog；显式更新 cost
    时若未提供 cost_source，默认标记为 user_input。
    """
    code = normalize_code(code)
    cost_before = _position_cost(manager, code)
    if "cost" in kwargs and "cost_source" not in kwargs:
        kwargs["cost_source"] = "user_input"
    manager._push_oplog("update_position", code=code, cost_before=cost_before)
    holder = {"r": None}

    def _apply(data: dict) -> dict:
        for p in data.get("positions", []):
            if p["code"].lower() == code:
                for key in (
                    "cost",
                    "quantity",
                    "name",
                    "buy_date",
                    "tags",
                    "cost_source",
                ):
                    if key in kwargs:
                        p[key] = kwargs[key]
                holder["r"] = p
                break
        return data

    if auto_save:
        manager.atomic_update(_apply)
    else:
        _apply(manager._data)
    r = holder["r"]
    if r is not None:
        manager._oplog_backfill(
            "update_position",
            cost_after=r.get("cost"),
            cost_source=r.get("cost_source"),
        )
    return r


def tag_position(
    manager: "PortfolioManager", code: str, *tags: str, auto_save: bool = True
) -> Optional[dict]:
    """给持仓添加标签。"""
    code = normalize_code(code)
    holder = {"r": None}

    def _apply(data: dict) -> dict:
        for p in data.get("positions", []):
            if p["code"].lower() == code:
                existing = set(p.get("tags", []))
                existing.update(tags)
                p["tags"] = sorted(existing)
                holder["r"] = p
                break
        return data

    if auto_save:
        manager.atomic_update(_apply)
    else:
        _apply(manager._data)
    return holder["r"]


def untag_position(
    manager: "PortfolioManager", code: str, *tags: str, auto_save: bool = True
) -> Optional[dict]:
    """移除持仓标签。"""
    code = normalize_code(code)
    holder = {"r": None}

    def _apply(data: dict) -> dict:
        for p in data.get("positions", []):
            if p["code"].lower() == code:
                existing = set(p.get("tags", []))
                existing -= set(tags)
                p["tags"] = sorted(existing)
                holder["r"] = p
                break
        return data

    if auto_save:
        manager.atomic_update(_apply)
    else:
        _apply(manager._data)
    return holder["r"]


def add_watch(
    manager: "PortfolioManager",
    code: str,
    name: str = "",
    target_buy: float = 0,
    target_sell: float = 0,
    auto_save: bool = True,
) -> dict:
    """添加自选股。"""
    code = normalize_code(code)
    manager._push_oplog("add_watch", code=code)
    holder = {}

    def _apply(data: dict) -> dict:
        watchlist = data.setdefault("watchlist", [])
        existing = None
        for w in watchlist:
            if w["code"].lower() == code:
                existing = w
                break
        if existing:
            if name:
                existing["name"] = name
            if target_buy:
                existing["target_buy"] = target_buy
            if target_sell:
                existing["target_sell"] = target_sell
            holder["r"] = existing
        else:
            new_watch = {
                "code": code,
                "name": name or "",
                "target_buy": target_buy,
                "target_sell": target_sell,
                "added_date": _today(),
            }
            watchlist.append(new_watch)
            holder["r"] = new_watch
        return data

    if auto_save:
        manager.atomic_update(_apply)
    else:
        _apply(manager._data)
    return holder["r"]


def remove_watch(
    manager: "PortfolioManager", code: str, auto_save: bool = True
) -> bool:
    """移除自选股。"""
    code = normalize_code(code)
    manager._push_oplog("remove_watch", code=code)
    holder = {"found": False}

    def _apply(data: dict) -> dict:
        watchlist = data.get("watchlist", [])
        for i, w in enumerate(watchlist):
            if w["code"].lower() == code:
                watchlist.pop(i)
                holder["found"] = True
                return data
        return data

    if auto_save:
        manager.atomic_update(_apply)
    else:
        _apply(manager._data)
    return holder["found"]


__all__ = [
    "add_position",
    "reduce_position",
    "remove_position",
    "update_position",
    "tag_position",
    "untag_position",
    "add_watch",
    "remove_watch",
]
