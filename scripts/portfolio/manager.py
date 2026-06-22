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

import copy
import json
import os
import tempfile
from datetime import datetime
from contextlib import contextmanager
from pathlib import Path
from typing import Optional


def _data_dir() -> Path:
    """返回 scripts/data 目录。"""
    return Path(__file__).resolve().parent.parent / "data"


def _portfolio_path() -> Path:
    return _data_dir() / "portfolio.json"


def _example_path() -> Path:
    return _data_dir() / "portfolio_example.json"


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _lock_path(path: Path) -> Path:
    """返回与数据文件对应的锁文件路径。"""
    return path.parent / f".{path.stem}.lock"


@contextmanager
def _file_lock(path: Path, timeout: float = 10.0):
    """基于文件锁的并发保护机制。

    Args:
        path: 数据文件路径
        timeout: 获取锁超时时间（秒）

    Raises:
        TimeoutError: 获取锁超时
        OSError: 锁文件操作失败
    """
    lock_path = _lock_path(path)
    lock_fd = None
    start_time = datetime.now().timestamp()

    try:
        # 尝试获取锁
        while True:
            try:
                # O_CREAT | O_EXCL: 原子创建，如果已存在则失败
                lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                # 锁已存在，检查是否超时
                if datetime.now().timestamp() - start_time > timeout:
                    raise TimeoutError(f"获取锁超时: {lock_path}")
                # 短暂等待后重试
                import time

                time.sleep(0.05)

        yield  # 锁获取成功，执行操作

    finally:
        # 释放锁
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except OSError:
                pass
        try:
            os.unlink(str(lock_path))
        except OSError:
            pass


def _raw_write(path: Path, data: dict) -> None:
    """底层写入（调用方需已持锁）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _atomic_write(path: Path, data: dict) -> None:
    """原子写入 JSON 文件（加锁保护）。"""
    with _file_lock(path):
        _raw_write(path, data)


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
        """按代码查找持仓（返回副本，防止外部意外修改内部状态）。"""
        p = self._find_position(code)
        return copy.deepcopy(p) if p else None

    def _find_watch(self, code: str) -> Optional[dict]:
        """按代码查找自选（内部引用，用于修改）。"""
        code = code.lower()
        for w in self.get_watchlist():
            if w["code"].lower() == code:
                return w
        return None

    def get_watch(self, code: str) -> Optional[dict]:
        """按代码查找自选（返回副本，防止外部意外修改内部状态）。"""
        w = self._find_watch(code)
        return copy.deepcopy(w) if w else None

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
        existing = self._find_position(code)

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
            result = existing
        else:
            result = {
                "code": code,
                "name": name or "",
                "cost": round(cost, 3),
                "quantity": quantity,
                "buy_date": buy_date or _today(),
                "tags": tags or [],
            }
            self._data.setdefault("positions", []).append(result)

        if auto_save:
            self.save()
        return result

    def reduce_position(
        self, code: str, quantity: int, auto_save: bool = True
    ) -> Optional[dict]:
        """减仓。返回减仓后的持仓信息，如果全部卖出则移除。"""
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        code = code.lower()
        positions = self._data.get("positions", [])
        for i, p in enumerate(positions):
            if p["code"].lower() == code:
                p["quantity"] -= quantity
                if p["quantity"] <= 0:
                    positions.pop(i)
                    return None
                if auto_save:
                    self.save()
                return p
        return None

    def remove_position(self, code: str, auto_save: bool = True) -> bool:
        """清仓（移除持仓）。"""
        code = code.lower()
        positions = self._data.get("positions", [])
        for i, p in enumerate(positions):
            if p["code"].lower() == code:
                positions.pop(i)
                if auto_save:
                    self.save()
                return True
        return False

    def update_position(
        self, code: str, auto_save: bool = True, **kwargs
    ) -> Optional[dict]:
        """更新持仓字段（cost, quantity, name, buy_date, tags）。"""
        code = code.lower()
        p = self._find_position(code)
        if not p:
            return None
        for key in ("cost", "quantity", "name", "buy_date", "tags"):
            if key in kwargs:
                p[key] = kwargs[key]
        if auto_save:
            self.save()
        return p

    def tag_position(
        self, code: str, *tags: str, auto_save: bool = True
    ) -> Optional[dict]:
        """给持仓添加标签。"""
        code = code.lower()
        p = self._find_position(code)
        if not p:
            return None
        existing = set(p.get("tags", []))
        existing.update(tags)
        p["tags"] = sorted(existing)
        if auto_save:
            self.save()
        return p

    def untag_position(
        self, code: str, *tags: str, auto_save: bool = True
    ) -> Optional[dict]:
        """移除持仓标签。"""
        code = code.lower()
        p = self._find_position(code)
        if not p:
            return None
        existing = set(p.get("tags", []))
        existing -= set(tags)
        p["tags"] = sorted(existing)
        if auto_save:
            self.save()
        return p

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
        existing = self._find_watch(code)
        if existing:
            if name:
                existing["name"] = name
            if target_buy:
                existing["target_buy"] = target_buy
            if target_sell:
                existing["target_sell"] = target_sell
            result = existing
        else:
            result = {
                "code": code,
                "name": name or "",
                "target_buy": target_buy,
                "target_sell": target_sell,
                "added_date": _today(),
            }
            self._data.setdefault("watchlist", []).append(result)

        if auto_save:
            self.save()
        return result

    def remove_watch(self, code: str, auto_save: bool = True) -> bool:
        """移除自选股。"""
        code = code.lower()
        watchlist = self._data.get("watchlist", [])
        for i, w in enumerate(watchlist):
            if w["code"].lower() == code:
                watchlist.pop(i)
                if auto_save:
                    self.save()
                return True
        return False

    # ---------- 导入导出 ----------

    def export_codes(self) -> list:
        """导出所有持仓代码列表（兼容旧接口）。"""
        return [p["code"] for p in self.get_positions()]

    def to_dict(self) -> dict:
        """返回完整数据副本。"""
        return copy.deepcopy(self._data)

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
