"""交易日志模块。

记录清仓操作到 scripts/data/trade_log.json。
支持自动记录和历史查询，数据格式向后兼容。

用法:
    from portfolio.trade_log import TradeLog

    tl = TradeLog()
    tl.record(code="sh600989", name="宝丰能源", buy_date="2025-03-15",
              cost=18.5, quantity=1000, sell_price=22.0)
    history = tl.query()
    history = tl.query(code="sh600989")
    stats = tl.stats()
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from common.validators import normalize_code
from portfolio._file_utils import (
    atomic_write,
    data_dir,
    file_lock,
    raw_write,
    today as _today,
)


def _trade_log_path() -> Path:
    return data_dir() / "trade_log.json"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# 向后兼容别名
_data_dir = data_dir
_file_lock = file_lock
_raw_write = raw_write
_atomic_write = atomic_write


class TradeLog:
    """交易日志管理器。

    记录清仓操作，支持历史查询和统计分析。
    数据文件格式向后兼容，自动处理缺失字段。
    """

    def __init__(self, path: Optional[str] = None):
        """初始化交易日志。

        Args:
            path: 自定义日志文件路径，默认 scripts/data/trade_log.json
        """
        self._path = Path(path) if path else _trade_log_path()
        self._data = self._load()

    def _load(self) -> dict:
        """加载日志文件，处理向后兼容。"""
        if not self._path.exists():
            return {"version": 1, "records": []}

        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"version": 1, "records": []}

        # 向后兼容：如果没有 version 字段，视为 v1
        if "version" not in data:
            data["version"] = 1

        # 确保 records 字段存在
        if "records" not in data:
            data["records"] = []

        # 补全旧记录的缺失字段（向后兼容）
        for record in data["records"]:
            record.setdefault("reason", "manual")
            record.setdefault("timestamp", record.get("sell_date", "") + "T00:00:00")
            record.setdefault("sell_price", 0.0)
            record.setdefault("profit", 0.0)
            record.setdefault("profit_pct", 0.0)

        return data

    def save(self) -> None:
        """持久化到文件。"""
        _atomic_write(self._path, self._data)

    def reload(self) -> None:
        """重新从磁盘加载数据。"""
        self._data = self._load()

    def record(
        self,
        code: str,
        name: str = "",
        buy_date: str = "",
        cost: float = 0.0,
        quantity: int = 0,
        sell_price: float = 0.0,
        sell_date: str = "",
        reason: str = "manual",
        auto_save: bool = True,
    ) -> dict:
        """记录一笔清仓交易。

        Args:
            code: 股票代码
            name: 股票名称
            buy_date: 买入日期
            cost: 买入成本（每股）
            quantity: 卖出数量
            sell_price: 卖出价格（每股），0 表示未知
            sell_date: 卖出日期，默认今天
            reason: 清仓原因（manual/reduce_to_zero/web_remove）
            auto_save: 是否自动保存

        Returns:
            新增的交易记录
        """
        code = normalize_code(code)
        sell_date = sell_date or _today()

        # 计算盈亏
        if sell_price > 0 and cost > 0 and quantity > 0:
            profit = round((sell_price - cost) * quantity, 2)
            profit_pct = round((sell_price / cost - 1) * 100, 2)
        else:
            profit = 0.0
            profit_pct = 0.0

        record = {
            "code": code,
            "name": name or "",
            "buy_date": buy_date or "",
            "cost": round(cost, 3),
            "quantity": quantity,
            "sell_date": sell_date,
            "sell_price": round(sell_price, 3),
            "profit": profit,
            "profit_pct": profit_pct,
            "reason": reason,
            "timestamp": _now_iso(),
        }

        self._data.setdefault("records", []).append(record)

        if auto_save:
            # P0-7: 在锁内重读磁盘+追加+写回，避免并发 record() 后写者覆盖前者
            with _file_lock(self._path, timeout=5.0):
                latest = self._load()
                latest.setdefault("records", []).append(record)
                _raw_write(self._path, latest)
            self._data = latest

        return record

    def query(
        self,
        code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
    ) -> list:
        """查询历史交易记录。

        Args:
            code: 按股票代码过滤
            start_date: 按卖出日期范围过滤（起始，含）
            end_date: 按卖出日期范围过滤（结束，含）
            limit: 返回记录数上限

        Returns:
            交易记录列表（按卖出日期降序）
        """
        records = self._data.get("records", [])

        # 按代码过滤
        if code:
            code = normalize_code(code)
            records = [r for r in records if r.get("code", "") == code]

        # 按日期范围过滤
        if start_date:
            records = [r for r in records if r.get("sell_date", "") >= start_date]
        if end_date:
            records = [r for r in records if r.get("sell_date", "") <= end_date]

        # 按卖出日期降序排序
        records.sort(key=lambda r: r.get("sell_date", ""), reverse=True)

        return records[:limit]

    def stats(self) -> dict:
        """统计交易数据。"""
        records = self._data.get("records", [])
        if not records:
            return {
                "total_trades": 0,
                "total_profit": 0.0,
                "win_trades": 0,
                "loss_trades": 0,
                "win_rate": 0.0,
                "avg_profit": 0.0,
                "max_profit": 0.0,
                "max_loss": 0.0,
                "best_trade": None,
                "worst_trade": None,
                "by_stock": {},
            }

        profits = [r.get("profit", 0) for r in records]
        total_profit = sum(profits)
        win_trades = sum(1 for p in profits if p > 0)
        loss_trades = sum(1 for p in profits if p < 0)

        best_idx = profits.index(max(profits)) if profits else 0
        worst_idx = profits.index(min(profits)) if profits else 0

        # 按股票分组统计
        by_stock = {}
        for r in records:
            code = r.get("code", "")
            if code not in by_stock:
                by_stock[code] = {
                    "name": r.get("name", ""),
                    "trades": 0,
                    "total_profit": 0.0,
                    "total_quantity": 0,
                }
            by_stock[code]["trades"] += 1
            by_stock[code]["total_profit"] += r.get("profit", 0)
            by_stock[code]["total_quantity"] += r.get("quantity", 0)
            if r.get("name"):
                by_stock[code]["name"] = r["name"]

        for v in by_stock.values():
            v["total_profit"] = round(v["total_profit"], 2)

        return {
            "total_trades": len(records),
            "total_profit": round(total_profit, 2),
            "win_trades": win_trades,
            "loss_trades": loss_trades,
            "win_rate": round(win_trades / len(records) * 100, 1) if records else 0.0,
            "avg_profit": round(total_profit / len(records), 2) if records else 0.0,
            "max_profit": round(max(profits), 2) if profits else 0.0,
            "max_loss": round(min(profits), 2) if profits else 0.0,
            "best_trade": records[best_idx] if records else None,
            "worst_trade": records[worst_idx] if records else None,
            "by_stock": by_stock,
        }

    def summary(self) -> str:
        """返回交易日志摘要文本。"""
        s = self.stats()
        if s["total_trades"] == 0:
            return "暂无交易记录"

        lines = [
            f"交易记录: {s['total_trades']} 笔",
            f"总盈亏: {'+' if s['total_profit'] >= 0 else ''}{s['total_profit']:,.2f} 元",
            f"胜率: {s['win_rate']}% ({s['win_trades']}盈 / {s['loss_trades']}亏)",
            f"平均盈亏: {'+' if s['avg_profit'] >= 0 else ''}{s['avg_profit']:,.2f} 元",
        ]

        if s["best_trade"]:
            bt = s["best_trade"]
            lines.append(
                f"最佳: {bt.get('name') or bt['code']} "
                f"+{bt.get('profit', 0):,.2f}元 ({bt.get('profit_pct', 0):+.1f}%)"
            )
        if s["worst_trade"]:
            wt = s["worst_trade"]
            if wt.get("profit", 0) < 0:
                lines.append(
                    f"最差: {wt.get('name') or wt['code']} "
                    f"{wt.get('profit', 0):,.2f}元 ({wt.get('profit_pct', 0):+.1f}%)"
                )

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """返回完整数据副本。"""
        import copy

        return copy.deepcopy(self._data)
