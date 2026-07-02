"""持仓组合管理器。

v2 数据模型：
{
  "version": 2,
  "positions": [
    {"code": "sh600989", "name": "宝丰能源", "cost": 18.50, "quantity": 1000, "buy_date": "2025-03-15", "tags": ["能源", "长线"]}
  ],
  "watchlist": [
    {"code": "sz000807", "name": "云铝股份", "target_buy": 12.00, "target_sell": 16.00, "added_date": "2025-06-01"}
  ]
}

向后兼容 v1 格式（只有 codes 列表）。
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from portfolio._file_utils import (
    atomic_write,
    data_dir,
    file_lock,
    raw_write,
    today as _today,
)


def _portfolio_path() -> Path:
    return data_dir() / "portfolio.json"


def _example_path() -> Path:
    return data_dir() / "portfolio_example.json"


# 向后兼容别名
_data_dir = data_dir
_file_lock = file_lock
_raw_write = raw_write
_atomic_write = atomic_write


def _atomic_read(path: Path) -> dict:
    """原子读取 JSON 文件（已加锁保护）。"""
    with _file_lock(path, timeout=5.0):
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))


class PortfolioManager:
    """持仓组合管理器。

    支持并发写入：通过文件锁机制防止多进程同时修改导致数据覆盖。
    支持虚拟持仓：virtual=True 时使用 portfolio_virtual.json（模拟盘）。
    """

    def __init__(self, path: Optional[str] = None, virtual: bool = False):
        if path:
            self._path = Path(path)
        elif virtual:
            self._path = _data_dir() / "portfolio_virtual.json"
        else:
            self._path = _portfolio_path()
        self._is_example = False
        self._is_virtual = virtual
        self._data = self._load()

    def _load(self) -> dict:
        """加载持仓文件，自动兼容 v1 格式。"""
        if not self._path.exists():
            # 回退到示例文件
            ex = _example_path()
            if ex.exists():
                data = json.loads(ex.read_text(encoding="utf-8"))
                self._is_example = True
            else:
                data = {"version": 2, "positions": [], "watchlist": []}
                self._is_example = True
        else:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._is_example = False

        # v1 向后兼容：只有 codes 列表
        if data.get("version", 1) == 1 and "codes" in data:
            data = self._migrate_v1(data)

        return data

    def _migrate_v1(self, data: dict) -> dict:
        """将 v1 格式迁移为 v2。"""
        positions = []
        for code in data.get("codes", []):
            positions.append(
                {
                    "code": code,
                    "name": "",
                    "cost": 0,
                    "quantity": 0,
                    "buy_date": "",
                    "tags": [],
                }
            )
        return {
            "version": 2,
            "positions": positions,
            "watchlist": [],
        }

    def save(self) -> None:
        """持久化到文件（已加锁保护）。"""
        _atomic_write(self._path, self._data)

    def reload(self) -> None:
        """重新从磁盘加载数据（用于外部修改后的同步）。"""
        with _file_lock(self._path, timeout=5.0):
            self._data = self._load()

    @property
    def is_virtual(self) -> bool:
        """是否为虚拟持仓（模拟盘）。"""
        return self._is_virtual

    @property
    def portfolio_type(self) -> str:
        """返回持仓类型标签。"""
        return "虚拟持仓" if self._is_virtual else "实盘持仓"

    @property
    def data_path(self) -> str:
        """返回数据文件路径。"""
        return str(self._path)

    def atomic_update(self, updater: callable) -> None:
        """原子性地执行数据更新操作。

        Args:
            updater: 接受当前数据 dict，返回修改后的数据 dict

        Example:
            pm.atomic_update(lambda data: data.setdefault("positions", []).append(new_pos))
        """
        with _file_lock(self._path):
            # 重新加载最新数据（_load 内部不获取锁，避免死锁）
            self._data = self._load()
            # 执行更新
            self._data = updater(self._data)
            # 写回（使用 _raw_write，因为已持锁）
            _raw_write(self._path, self._data)

    # ---------- 查询 ----------

    @property
    def is_example(self) -> bool:
        """是否加载的是示例数据（portfolio.json 不存在时回退到示例文件）。"""
        return self._is_example

    def get_positions(self) -> list:
        """返回全部持仓。"""
        return self._data.get("positions", [])

    def get_watchlist(self) -> list:
        """返回全部自选。"""
        return self._data.get("watchlist", [])

    def _find_position(self, code: str) -> Optional[dict]:
        """按代码查找持仓（内部引用，用于修改）。"""
        code = code.lower()
        for p in self.get_positions():
            if p["code"].lower() == code:
                return p
        return None

    def get_position(self, code: str) -> Optional[dict]:
        """按代码查找持仓（返回浅副本，防止外部意外修改内部状态）。"""
        p = self._find_position(code)
        return dict(p) if p else None

    def _find_watch(self, code: str) -> Optional[dict]:
        """按代码查找自选（内部引用，用于修改）。"""
        code = code.lower()
        for w in self.get_watchlist():
            if w["code"].lower() == code:
                return w
        return None

    def get_watch(self, code: str) -> Optional[dict]:
        """按代码查找自选（返回浅副本，防止外部意外修改内部状态）。"""
        w = self._find_watch(code)
        return dict(w) if w else None

    def get_all_codes(self) -> list:
        """返回所有持仓 + 自选的代码列表。"""
        codes = [p["code"] for p in self.get_positions()]
        codes += [w["code"] for w in self.get_watchlist()]
        return codes

    # ---------- 持仓操作 ----------

    def add_position(
        self,
        code: str,
        name: str,
        cost: float,
        quantity: int,
        buy_date: str = "",
        tags: list = None,
        auto_save: bool = True,
    ) -> dict:
        """添加持仓。如果已存在则加仓（加权平均成本）。"""
        code = code.lower()
        result_holder = {}

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
                }
                positions.append(new_pos)
                result_holder["r"] = new_pos
            return data

        if auto_save:
            self.atomic_update(_apply)
        else:
            _apply(self._data)
        return result_holder["r"]

    def reduce_position(
        self, code: str, quantity: int, auto_save: bool = True, sell_price: float = None
    ) -> Optional[dict]:
        """减仓。返回减仓后的持仓信息，如果全部卖出则移除并记录交易日志。"""
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        code = code.lower()
        result_holder = {"r": None, "cleared": False, "pos": None}

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
            self.atomic_update(_apply)
        else:
            _apply(self._data)

        # 交易日志在锁外记录（独立文件，失败不阻塞持仓操作）
        pos = result_holder.get("pos")
        actual_qty = result_holder.get("actual_qty", 0)
        if pos is not None:
            if result_holder.get("cleared"):
                self._record_trade_log(
                    code,
                    pos.get("name", ""),
                    pos.get("cost", 0),
                    actual_qty,
                    reason="reduce_to_zero",
                    sell_price=sell_price,
                )
            elif sell_price:
                self._record_trade_log(
                    code,
                    pos.get("name", ""),
                    pos.get("cost", 0),
                    actual_qty,
                    reason="partial_reduce",
                    sell_price=sell_price,
                )
        return result_holder["r"]

    def remove_position(self, code: str, auto_save: bool = True) -> bool:
        """清仓（移除持仓）并记录交易日志。"""
        code = code.lower()
        holder = {"found": False, "pos": None}

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
            self.atomic_update(_apply)
        else:
            _apply(self._data)

        if holder["found"] and holder["pos"] is not None:
            p = holder["pos"]
            self._record_trade_log(
                code,
                p.get("name", ""),
                p.get("cost", 0),
                p.get("quantity", 0),
                reason="manual",
            )
        return holder["found"]

    def _record_trade_log(
        self,
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

    def update_position(
        self, code: str, auto_save: bool = True, **kwargs
    ) -> Optional[dict]:
        """更新持仓字段（cost, quantity, name, buy_date, tags）。"""
        code = code.lower()
        holder = {"r": None}

        def _apply(data: dict) -> dict:
            for p in data.get("positions", []):
                if p["code"].lower() == code:
                    for key in ("cost", "quantity", "name", "buy_date", "tags"):
                        if key in kwargs:
                            p[key] = kwargs[key]
                    holder["r"] = p
                    break
            return data

        if auto_save:
            self.atomic_update(_apply)
        else:
            _apply(self._data)
        return holder["r"]

    def tag_position(
        self, code: str, *tags: str, auto_save: bool = True
    ) -> Optional[dict]:
        """给持仓添加标签。"""
        code = code.lower()
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
            self.atomic_update(_apply)
        else:
            _apply(self._data)
        return holder["r"]

    def untag_position(
        self, code: str, *tags: str, auto_save: bool = True
    ) -> Optional[dict]:
        """移除持仓标签。"""
        code = code.lower()
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
            self.atomic_update(_apply)
        else:
            _apply(self._data)
        return holder["r"]

    # ---------- 自选操作 ----------

    def add_watch(
        self,
        code: str,
        name: str = "",
        target_buy: float = 0,
        target_sell: float = 0,
        auto_save: bool = True,
    ) -> dict:
        """添加自选股。"""
        code = code.lower()
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
            self.atomic_update(_apply)
        else:
            _apply(self._data)
        return holder["r"]

    def remove_watch(self, code: str, auto_save: bool = True) -> bool:
        """移除自选股。"""
        code = code.lower()
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
            self.atomic_update(_apply)
        else:
            _apply(self._data)
        return holder["found"]

    # ---------- 导入导出 ----------

    def export_codes(self) -> list:
        """导出所有持仓代码列表（兼容旧接口）。"""
        return [p["code"] for p in self.get_positions()]

    def check_concentration(
        self,
        single_stock_limit: float = 0.20,
        top3_limit: float = 0.50,
        industry_limit: float = 0.30,
    ) -> dict:
        """检查持仓集中度。

        Args:
            single_stock_limit: 单一标的上限（默认 20%）
            top3_limit: 前 3 大持仓上限（默认 50%）
            industry_limit: 单一行业上限（默认 30%）

        Returns:
            {"warnings": [str], "details": {"single": {...}, "top3": {...}, "industry": {...}}}
        """
        positions = self.get_positions()
        if not positions:
            return {"warnings": [], "details": {}}

        total_value = sum(p.get("cost", 0) * p.get("quantity", 0) for p in positions)
        if total_value <= 0:
            return {"warnings": [], "details": {}}

        warnings = []
        details = {}

        # 单一标的集中度
        stock_pcts = []
        for p in positions:
            value = p.get("cost", 0) * p.get("quantity", 0)
            pct = value / total_value
            stock_pcts.append(
                {"code": p["code"], "name": p.get("name", ""), "pct": pct}
            )
        stock_pcts.sort(key=lambda x: x["pct"], reverse=True)

        if stock_pcts:
            top1 = stock_pcts[0]
            details["single"] = {
                "code": top1["code"],
                "pct": round(top1["pct"] * 100, 1),
            }
            if top1["pct"] > single_stock_limit:
                warnings.append(
                    f"单一标的集中度 {top1['pct']*100:.1f}% > {single_stock_limit*100:.0f}%"
                    f"（{top1['name'] or top1['code']}）"
                )

        # 前 3 大持仓集中度
        top3_value = sum(s["pct"] for s in stock_pcts[:3])
        details["top3"] = {"pct": round(top3_value * 100, 1)}
        if top3_value > top3_limit:
            warnings.append(
                f"前3大持仓集中度 {top3_value*100:.1f}% > {top3_limit*100:.0f}%"
            )

        # 行业集中度
        industry_values = {}
        for p in positions:
            # 从 tags 中提取行业标签
            tags = p.get("tags", [])
            industry = tags[0] if tags else "未分类"
            value = p.get("cost", 0) * p.get("quantity", 0)
            industry_values[industry] = industry_values.get(industry, 0) + value

        industry_pcts = {k: v / total_value for k, v in industry_values.items()}
        details["industry"] = {k: round(v * 100, 1) for k, v in industry_pcts.items()}

        for ind, pct in industry_pcts.items():
            if pct > industry_limit:
                warnings.append(
                    f"行业集中度 {ind}: {pct*100:.1f}% > {industry_limit*100:.0f}%"
                )

        return {"warnings": warnings, "details": details}

    def to_dict(self) -> dict:
        """返回完整数据浅副本（positions/watchlist 为新列表，元素为共享引用）。"""
        d = dict(self._data)
        if "positions" in d:
            d["positions"] = list(d["positions"])
        if "watchlist" in d:
            d["watchlist"] = list(d["watchlist"])
        return d

    def summary(self) -> str:
        """返回持仓摘要文本。"""
        pos = self.get_positions()
        watch = self.get_watchlist()
        lines = [f"持仓 {len(pos)} 只，自选 {len(watch)} 只"]
        if pos:
            lines.append(
                "持仓: "
                + ", ".join(
                    f"{p.get('name') or p['code']}({p['quantity']}股)" for p in pos
                )
            )
        if watch:
            lines.append(
                "自选: " + ", ".join(w.get("name") or w["code"] for w in watch)
            )
        return "\n".join(lines)
