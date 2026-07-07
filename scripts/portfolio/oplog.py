"""操作日志模块（支持 undo 回滚）。

每次持仓/自选修改前，自动保存操作前的完整快照到 portfolio_oplog.json。
undo 时恢复最近一次快照，实现误操作回滚。

v2.4.0 新增：解决 portfolio 误操作不可恢复的问题。

用法:
    from portfolio.oplog import OpLog

    ol = OpLog()
    ol.push("add_position", code="sh600989", snapshot_before={...})
    ol.undo()  # 恢复最近快照
    ol.history()  # 查看操作历史
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from portfolio._file_utils import atomic_write, data_dir, file_lock


def _oplog_path() -> Path:
    return data_dir() / "portfolio_oplog.json"


_MAX_HISTORY = 50  # 最多保留 50 条操作记录


class OpLog:
    """操作日志管理器。

    数据格式:
    {
        "version": 1,
        "entries": [
            {
                "op": "add_position",
                "timestamp": "2026-07-07T16:30:00",
                "code": "sh600989",
                "snapshot_before": {...}  # 操作前的完整 portfolio 数据
            }
        ]
    }
    """

    def __init__(self, path: Optional[str] = None):
        self._path = Path(path) if path else _oplog_path()
        self._data = self._load()

    def _load(self) -> dict:
        if not self._path.exists():
            return {"version": 1, "entries": []}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"version": 1, "entries": []}
        data.setdefault("entries", [])
        return data

    def save(self) -> None:
        atomic_write(self._path, self._data)

    def push(
        self,
        op: str,
        code: str = "",
        snapshot_before: dict = None,
        auto_save: bool = True,
    ) -> dict:
        """记录一次操作。

        Args:
            op: 操作类型（add_position / reduce_position / remove_position / add_watch / remove_watch）
            code: 股票代码
            snapshot_before: 操作前的完整 portfolio 数据快照
            auto_save: 是否自动保存

        Returns:
            新增的操作记录
        """
        entry = {
            "op": op,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "code": code,
            "snapshot_before": snapshot_before or {},
        }
        self._data["entries"].append(entry)

        # 保留最近 N 条
        if len(self._data["entries"]) > _MAX_HISTORY:
            self._data["entries"] = self._data["entries"][-_MAX_HISTORY:]

        if auto_save:
            self.save()
        return entry

    def undo(self) -> Optional[dict]:
        """回滚最近一次操作，返回其 snapshot_before。

        Returns:
            最近操作的 snapshot_before（用于恢复 portfolio），无记录时返回 None
        """
        entries = self._data.get("entries", [])
        if not entries:
            return None

        last = entries.pop()
        self.save()
        return last.get("snapshot_before")

    def peek(self) -> Optional[dict]:
        """查看最近一次操作记录（不删除）。"""
        entries = self._data.get("entries", [])
        return entries[-1] if entries else None

    def history(self, limit: int = 20) -> list:
        """查看操作历史（最近 N 条，不删除）。"""
        entries = self._data.get("entries", [])
        return entries[-limit:]

    def clear(self) -> None:
        """清空操作历史。"""
        self._data["entries"] = []
        self.save()

    def to_dict(self) -> dict:
        """返回完整数据副本。"""
        import copy
        return copy.deepcopy(self._data)
