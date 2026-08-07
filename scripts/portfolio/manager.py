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

v2.4.0：每次修改操作前自动 push 快照到 OpLog，支持 undo 回滚。
"""

import json
import logging
from pathlib import Path
from typing import Optional

from common.validators import normalize_code

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


def _file_mtime(path: Path) -> str:
    """返回文件 mtime 的 ISO 字符串（健康检查报告用）。"""
    try:
        from datetime import datetime
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, FileNotFoundError):
        return ""


class PortfolioManager:
    """持仓组合管理器。

    支持并发写入：通过文件锁机制防止多进程同时修改导致数据覆盖。
    支持虚拟持仓：virtual=True 时使用 portfolio_virtual.json（模拟盘）。
    """

    # 状态类标签白名单：tags[0] 是这类时不当作行业，避免
    # 宝丰能源 tags=["T+1待交收","煤化工","能源"] 被错误归类
    _STATUS_TAGS = frozenset({
        "T+1待交收", "T+1", "长线", "短线", "核心", "卫星",
        "底仓", "波段", "网格", "定投", "观察", "待加仓",
    })

    # 行业子标签 → 行业大类映射：合并锂电产业链分散标签，
    # 避免 tags[0]="锂矿/锂业/储能/光伏/新能源/有色" 被分散成多个行业。
    _INDUSTRY_GROUP = {
        # 锂/新能源链分散子标签合并到"锂/新能源"大类
        "锂电": "锂/新能源", "锂矿": "锂/新能源", "锂业": "锂/新能源",
        "锂电池": "锂/新能源",
        "新能源": "锂/新能源",  # 泛指归入锂/新能源大类
        "光伏": "锂/新能源", "储能": "锂/新能源",
        "新能源车": "锂/新能源", "新能源ETF": "锂/新能源",
        "钴": "锂/新能源", "镍": "锂/新能源",
        # 其他合并
        "海缆": "通信",
        "机器人": "汽零/工业",  # robot → 汽零工业大类
    }

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

    def _load(self, acquire_lock: bool = True) -> dict:
        """加载持仓文件，自动兼容 v1 格式。

        Args:
            acquire_lock: 是否获取文件锁。调用方已持锁时传 False 避免死锁。
        """

        def _do_load() -> dict:
            if not self._path.exists():
                # 回退到示例文件
                ex = _example_path()
                if ex.exists():
                    data = json.loads(ex.read_text(encoding="utf-8"))
                    self._is_example = True
                else:
                    # 全新空 portfolio（非示例数据），避免误标 is_example
                    data = {"version": 2, "positions": [], "watchlist": []}
                    self._is_example = False
            else:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._is_example = False

            # v1 向后兼容：只有 codes 列表
            if data.get("version", 1) == 1 and "codes" in data:
                data = self._migrate_v1(data)

            return data

        if acquire_lock:
            with _file_lock(self._path, timeout=5.0):
                return _do_load()
        return _do_load()

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
            self._data = self._load(acquire_lock=False)

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
            self._data = self._load(acquire_lock=False)
            # 执行更新
            self._data = updater(self._data)
            # 写回（使用 _raw_write，因为已持锁）
            _raw_write(self._path, self._data)

    def _push_oplog(self, op: str, code: str = "") -> None:
        """操作前推入快照到 OpLog（异常隔离，不影响主操作）。"""
        try:
            from portfolio.oplog import OpLog

            ol = OpLog()
            ol.push(op, code=code, snapshot_before=dict(self._data))
        except Exception as e:
            logger.debug("操作日志记录失败: %s", e)

    def undo(self) -> Optional[dict]:
        """回滚最近一次操作。

        从 OpLog 取出最近快照，恢复 portfolio 到操作前状态。

        Returns:
            被回滚的操作记录，无记录时返回 None
        """
        try:
            from portfolio.oplog import OpLog

            ol = OpLog()
            snapshot = ol.undo()
            if snapshot is None:
                return None
            # 恢复快照
            with _file_lock(self._path):
                _raw_write(self._path, snapshot)
            self._data = snapshot
            return {"restored": True, "timestamp": snapshot.get("timestamp", "")}
        except Exception as e:
            logger.debug("undo 失败: %s", e)
            return None

    def oplog_history(self, limit: int = 20) -> list:
        """查看操作历史。"""
        try:
            from portfolio.oplog import OpLog

            ol = OpLog()
            return ol.history(limit)
        except Exception as e:
            # v1.16.0 P1-2 MEDIUM
            from common.exceptions import log_silent_fallback

            log_silent_fallback(
                location="portfolio.manager.oplog_history",
                exception=e,
                fallback_reason="OpLog 历史不可用 → 用户无法 undo（数据丢失感知）",
            )
            return []

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
        code = normalize_code(code)
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
        code = normalize_code(code)
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
        code = normalize_code(code)
        self._push_oplog("add_position", code=code)
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
        code = normalize_code(code)
        self._push_oplog("reduce_position", code=code)
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
        code = normalize_code(code)
        self._push_oplog("remove_position", code=code)
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
        code = normalize_code(code)
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
            self.atomic_update(_apply)
        else:
            _apply(self._data)
        return holder["r"]

    def untag_position(
        self, code: str, *tags: str, auto_save: bool = True
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
        code = normalize_code(code)
        self._push_oplog("add_watch", code=code)
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
        code = normalize_code(code)
        self._push_oplog("remove_watch", code=code)
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

    # ---------- 分析（v1.17.0 P2-1 拆分预备：从 manager 抽到 portfolio.analytics） ----------

    def to_dict(self) -> dict:
        """返回完整数据浅副本（v1.16.0 thin wrapper → portfolio.analytics.to_dict）。"""
        from portfolio.analytics import to_dict as _to_dict

        return _to_dict(self)

    def summary(self) -> str:
        """返回持仓摘要文本（v1.16.0 thin wrapper → portfolio.analytics.summary）。"""
        from portfolio.analytics import summary as _summary

        return _summary(self)

    # ── 破位判定阈值 ──────────────────────────────────────────
    # 成本 -5% 视为破位（SKILL.md guardrails §四 + experts/risk_manager.md §四）
    BREAKDOWN_THRESHOLD = 0.95

    def health_report(
        self,
        quotes: Optional[dict] = None,
        breakdown_threshold: float = BREAKDOWN_THRESHOLD,
        top3_limit: float = 0.50,
        top5_limit: float = 0.70,
        industry_limit: float = 0.30,
        single_stock_limit: float = 0.20,
    ) -> dict:
        """标准化持仓健康检查报告（按 SKILL.md 模板结构）。

        输出结构化 dict，便于 SKILL 渲染与脚本抓取：
            {
                "as_of": "2026-08-07 10:30",
                "data_mtime": "2026-08-06 16:15",
                "type": "实盘/示例/虚拟",
                "totals": {"cost": ..., "value": ..., "pnl": ..., "pnl_pct": ...},
                "positions": [...],   # 每只含 breakdown 字段
                "watchlist": [...],
                "breakdown_positions": [...],   # 已破位独立汇总
                "concentration": {
                    "top3_pct": ..., "top5_pct": ...,
                    "single": {"code": ..., "name": ..., "pct": ...},
                    "industry": {"锂/新能源": 52.6, ...},
                },
                "warnings": [...],  # 集中度超阈值
                "risk_rating": "...",  # 一句话评级
                "thresholds": {  # 权威阈值来源（experts/risk_manager.md §四）
                    "top3": 50, "top5": 70, "industry": 30, "single": 20,
                },
            }

        Args:
            quotes: 实时行情 dict，键为代码（用 get_quotes 拉的 Quote.to_dict()）
            breakdown_threshold: 破位判定阈值（默认 0.95 = 成本 -5%）
            *_limit: 集中度阈值（默认与 experts/risk_manager.md §四 一致）
        """
        positions = self.get_positions()
        watchlist = self.get_watchlist()
        quotes_map = quotes or {}

        # 总成本/市值/盈亏
        total_cost = 0.0
        total_value = 0.0
        breakdown_positions = []
        position_rows = []

        for p in positions:
            code = p.get("code", "")
            name = p.get("name", code)
            cost = float(p.get("cost", 0) or 0)
            qty = int(p.get("quantity", 0) or 0)
            q = quotes_map.get(code, {})
            price = float(q.get("price", 0) or 0) if q else 0.0
            change_pct = float(q.get("change_pct", 0) or 0) if q else 0.0

            cost_value = cost * qty
            mv = price * qty
            pnl = mv - cost_value
            pnl_pct = (pnl / cost_value * 100) if cost_value else 0.0

            total_cost += cost_value
            total_value += mv

            breakdown = bool(
                cost > 0 and price > 0 and price < cost * breakdown_threshold
            )

            row = {
                "code": code,
                "name": name,
                "tags": p.get("tags", []),
                "price": round(price, 2),
                "cost": round(cost, 2),
                "qty": qty,
                "change_pct": round(change_pct, 2),
                "pnl": round(pnl, 0),
                "pnl_pct": round(pnl_pct, 2),
                "market_value": round(mv, 0),
                "breakdown": breakdown,
            }
            position_rows.append(row)
            if breakdown:
                breakdown_positions.append(row)

        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0.0

        # 自选股（带现价 + 距目标买卖的偏离）
        watch_rows = []
        for w in watchlist:
            code = w.get("code", "")
            name = w.get("name", code)
            q = quotes_map.get(code, {})
            price = float(q.get("price", 0) or 0) if q else 0.0
            tb = float(w.get("target_buy", 0) or 0)
            ts = float(w.get("target_sell", 0) or 0)
            watch_rows.append({
                "code": code,
                "name": name,
                "price": round(price, 2),
                "target_buy": tb,
                "target_sell": ts,
                "gap_to_buy_pct": round((price - tb) / tb * 100, 2) if tb else None,
                "gap_to_sell_pct": round((price - ts) / ts * 100, 2) if ts else None,
            })

        # 集中度（复用 check_concentration 的合并映射逻辑）
        # check_concentration 接受 code -> price 映射，需要从 quote_dict 提取
        price_map = {code: q.get("price", 0) for code, q in quotes_map.items() if code != "__as_of__"}
        concentration = self.check_concentration(
            quotes=price_map,
            top3_limit=top3_limit,
            industry_limit=industry_limit,
            single_stock_limit=single_stock_limit,
        )

        # 风险评级：一句话总结
        warnings = list(concentration.get("warnings", []))
        if breakdown_positions:
            warnings.insert(
                0,
                f"⚠️ {len(breakdown_positions)} 只标的破位："
                f"{', '.join(r['name'] for r in breakdown_positions)}",
            )
        risk_rating = "、".join(warnings) if warnings else "组合处于安全区间"

        return {
            "as_of": quotes_map.get("__as_of__", "") if quotes_map else "",
            "data_mtime": _file_mtime(self._path),
            "regime_hint": (
                "regime_state.json 非实时 regime，建议先 /market full 拉取最新市场状态"
                "（market_anchor 输出更准）"
            ),
            "screener_hint": (
                "⚠️ 锂/新能源链占比 30%+，建议先用 /screener --strategy quality_value "
                "筛医药/创新药/低相关防御板块，再叠加 /market 强弱板块确认"
            ),
            "totals": {
                "cost": round(total_cost, 0),
                "value": round(total_value, 0),
                "pnl": round(total_pnl, 0),
                "pnl_pct": round(total_pnl_pct, 2),
            },
            "type": self.portfolio_type,
            "positions": position_rows,
            "watchlist": watch_rows,
            "breakdown_positions": breakdown_positions,
            "concentration": concentration,
            "warnings": warnings,
            "risk_rating": risk_rating,
            "thresholds": {
                "top3": int(top3_limit * 100),
                "top5": int(top5_limit * 100),
                "industry": int(industry_limit * 100),
                "single": int(single_stock_limit * 100),
                "breakdown": f"成本×{breakdown_threshold:.2f}",
            },
        }

    def risk_summary(self, quotes: dict = None, confidence: float = 0.95) -> str:
        """持仓组合 VaR 风险摘要（v1.16.0 thin wrapper → portfolio.analytics.risk_summary）。"""
        from portfolio.analytics import risk_summary as _risk_summary

        return _risk_summary(self, quotes=quotes, confidence=confidence)

    def attribution_report(self, quotes: dict = None, period: str = "1M") -> str:
        """组合 Brinson 归因报告（v1.16.0 thin wrapper → portfolio.analytics.attribution_report）。"""
        from portfolio.analytics import attribution_report as _attribution_report

        return _attribution_report(self, quotes=quotes, period=period)

    def advisory_rebalance(
        self, target_ratio: float = 1.0, quotes: dict = None
    ) -> list:
        """调仓建议（v1.16.0 thin wrapper → portfolio.rebalance.advisory_rebalance）。"""
        from portfolio.rebalance import advisory_rebalance as _advisory_rebalance

        return _advisory_rebalance(self, target_ratio=target_ratio, quotes=quotes)

    # ---------- 导入导出 ----------

    def export_codes(self) -> list:
        """导出所有持仓代码列表（兼容旧接口）。"""
        return [p["code"] for p in self.get_positions()]

    def check_concentration(
        self,
        single_stock_limit: float = 0.20,
        top3_limit: float = 0.50,
        industry_limit: float = 0.30,
        quotes: dict = None,
    ) -> dict:
        """检查持仓集中度。

        Args:
            single_stock_limit: 单一标的上限（默认 20%）
            top3_limit: 前 3 大持仓上限（默认 50%）
            industry_limit: 单一行业上限（默认 30%）
            quotes: 可选 {code: current_price} 行情映射。提供时按市值（现价×数量）
                计算集中度，否则回退到成本口径。

        Returns:
            {"warnings": [str], "details": {"single": {...}, "top3": {...}, "industry": {...}}}
        """
        positions = self.get_positions()
        if not positions:
            return {"warnings": [], "details": {}}

        def _value(p) -> float:
            # P1-21: 优先用市值（现价×数量），无行情时回退成本口径
            if quotes and p["code"] in quotes:
                price = quotes[p["code"]] or 0
                return price * p.get("quantity", 0)
            return p.get("cost", 0) * p.get("quantity", 0)

        total_value = sum(_value(p) for p in positions)
        if total_value <= 0:
            return {"warnings": [], "details": {}}

        warnings = []
        details = {}

        # 单一标的集中度
        stock_pcts = []
        for p in positions:
            value = _value(p)
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
            # 从 tags 中提取行业标签：先过滤状态类标签，
            # 再尝试合并到行业大类（如"锂电/锂矿/锂业" → "锂/新能源"）。
            tags = p.get("tags", [])
            industry_tags = [t for t in tags if t not in self._STATUS_TAGS]
            if industry_tags:
                raw = industry_tags[0]
                industry = self._INDUSTRY_GROUP.get(raw, raw)
            elif tags:
                industry = tags[0]  # 全部是状态标签时的兜底
            else:
                industry = "未分类"
            value = _value(p)
            industry_values[industry] = industry_values.get(industry, 0) + value

        industry_pcts = {k: v / total_value for k, v in industry_values.items()}
        details["industry"] = {k: round(v * 100, 1) for k, v in industry_pcts.items()}

        for ind, pct in industry_pcts.items():
            if pct > industry_limit:
                warnings.append(
                    f"行业集中度 {ind}: {pct*100:.1f}% > {industry_limit*100:.0f}%"
                )

        return {"warnings": warnings, "details": details}
