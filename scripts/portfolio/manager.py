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
from typing import Any, Callable, Optional

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


class PortfolioManager:
    """持仓组合管理器。

    支持并发写入：通过文件锁机制防止多进程同时修改导致数据覆盖。
    支持虚拟持仓：virtual=True 时使用 portfolio_virtual.json（模拟盘）。
    """

    # 破位判定阈值：成本 × 0.95 = 成本 -5%
    # （SKILL.md guardrails §四 + experts/risk_manager.md §四）
    BREAKDOWN_THRESHOLD = 0.95

    # 状态类标签白名单：tags[0] 是这类时不当作行业，避免
    # 宝丰能源 tags=["T+1待交收","煤化工","能源"] 被错误归类
    _STATUS_TAGS = frozenset(
        {
            # 持有期/仓位类
            "T+1待交收",
            "T+1",
            "长线",
            "短线",
            "核心",
            "卫星",
            "底仓",
            "波段",
            "网格",
            "定投",
            "观察",
            "待加仓",
            "长持",
            "永持",
            "待止损",
            "待止盈",
            "已止盈",
            "对冲",
            "套保",
            "金字塔",
            "左侧",
            "右侧",
            # 投资风格类
            "白马",
            "价值",
            "蓝筹",
            "大盘",
            "红利",
            "高股息",
            "成长",
            "主题",
            "概念",
            "题材",
            "赛道",
            "科技",
            "趋势",
            "反转",
            "突破",
            "超跌",
            "低吸",
            "追涨",
            "短线投机",
            "打板",
            "涨停",
            "妖股",
            "壳资源",
            # 状态描述类
            "浮盈",
            "浮亏",
            "止损",
            "止盈",
        }
    )

    # 行业子标签 → 行业大类映射：合并分散标签到 6 大生态。
    # 避免 tags[0]="锂矿/锂业/储能/光伏/新能源/有色" 等被分散成多个行业。
    _INDUSTRY_GROUP = {
        # ── 锂/新能源链 ─────────────────────────────────
        "锂电": "锂/新能源",
        "锂矿": "锂/新能源",
        "锂业": "锂/新能源",
        "锂电池": "锂/新能源",
        "锂材料": "锂/新能源",
        "电池": "锂/新能源",
        "动力电池": "锂/新能源",
        "储能电池": "锂/新能源",
        "正极": "锂/新能源",
        "负极": "锂/新能源",
        "隔膜": "锂/新能源",
        "电解液": "锂/新能源",
        "三元": "锂/新能源",
        "磷酸铁锂": "锂/新能源",
        "电池片": "锂/新能源",
        "组件": "锂/新能源",
        "逆变器": "锂/新能源",
        "硅料": "锂/新能源",
        "硅片": "锂/新能源",
        "HJT": "锂/新能源",
        "TOPCon": "锂/新能源",
        "钙钛矿": "锂/新能源",
        "锂电正极": "锂/新能源",
        "新能源": "锂/新能源",
        "光伏": "锂/新能源",
        "储能": "锂/新能源",
        "新能源车": "锂/新能源",
        "新能源ETF": "锂/新能源",
        "钴": "锂/新能源",
        "镍": "锂/新能源",
        "有色": "锂/新能源",  # 锂/镍/钴等同属有色金属，合并到锂/新能源
        "风电": "锂/新能源",
        "核电": "锂/新能源",
        "氢能": "锂/新能源",
        # ── 半导体生态 ─────────────────────────────────
        "半导体": "半导体",
        "PCB": "半导体",
        "封测": "半导体",
        "IC设计": "半导体",
        "晶圆代工": "半导体",
        "光刻机": "半导体",
        "EDA": "半导体",
        "设备": "半导体",
        "材料": "半导体",
        # ── 医药生态 ─────────────────────────────────
        "医药": "医药",
        "创新药": "医药",
        "CRO": "医药",
        "CMO": "医药",
        "CDMO": "医药",
        "医疗器械": "医药",
        "仿制药": "医药",
        "中药": "医药",
        "生物制品": "医药",
        "原料药": "医药",
        # ── 消费生态 ─────────────────────────────────
        "白酒": "消费",
        "食品饮料": "消费",
        "家电": "消费",
        "美妆": "消费",
        "零售": "消费",
        "餐饮": "消费",
        "免税": "消费",
        "医美": "消费",
        "纺织服装": "消费",
        "宠物": "消费",
        # ── 金融生态 ─────────────────────────────────
        "银行": "金融",
        "证券": "金融",
        "保险": "金融",
        "信托": "金融",
        "金融科技": "金融",
        "租赁": "金融",
        "AMC": "金融",
        # ── 资源/周期生态 ─────────────────────────────
        "钢铁": "资源/周期",
        "煤炭": "资源/周期",
        "化工": "资源/周期",
        "建材": "资源/周期",
        "石油": "资源/周期",
        "黄金": "资源/周期",
        "稀土": "资源/周期",
        "铝": "资源/周期",
        "铜": "资源/周期",
        # ── 工业/制造 ─────────────────────────────────
        "海缆": "通信",
        "机器人": "汽零/工业",  # robot → 汽零工业大类
        "机械": "汽零/工业",
        "军工": "军工",
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
        """返回持仓类型标签（三态：实盘/虚拟/示例）。

        优先级：示例 > 虚拟 > 实盘。
        - 当 portfolio.json 不存在自动回退到 portfolio_example.json 时为"示例"
        - 显式 virtual=True 启动时为"虚拟"
        - 否则为"实盘"
        """
        if self._is_example:
            return "示例持仓"
        if self._is_virtual:
            return "虚拟持仓"
        return "实盘持仓"

    @property
    def data_path(self) -> str:
        """返回数据文件路径。"""
        return str(self._path)

    def atomic_update(self, updater: Callable[[dict], dict]) -> None:
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

    def _push_oplog(self, op: str, code: str = "", **extra) -> None:
        """操作前推入快照到 OpLog（异常隔离，不影响主操作）。"""
        try:
            from portfolio.oplog import OpLog

            ol = OpLog()
            ol.push(op, code=code, snapshot_before=dict(self._data), extra=extra or None)
        except Exception as e:
            logger.debug("操作日志记录失败: %s", e)

    def _oplog_backfill(self, op: str, **fields) -> None:
        """操作完成后回填最近一条 oplog 的 detail 字段（异常隔离）。"""
        try:
            from portfolio.oplog import OpLog

            OpLog().update_last(op=op, **fields)
        except Exception as e:
            logger.debug("操作日志回填失败: %s", e)

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
            # v1.16.0 MEDIUM
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

    def get_positions_with_pnl(self, price_lookup: Optional[dict] = None) -> list:
        """返回持仓+盈亏计算结果（为 market skill 持仓影响段提供完整数据）。

        Args:
            price_lookup: {code: price} 字典，若 None 则仅返回持仓基础数据
                （不含 current_price / pnl_pct / pnl_amount）。

        Returns:
            list[dict]: 每项包含 code/name/cost/quantity/buy_date/tags/board/industry
                以及可选字段 current_price / pnl_pct / pnl_amount。
        """
        import copy as _copy

        result = []
        for p in self.get_positions():
            row = _copy.copy(p)
            row["cost_total"] = round(p["cost"] * p["quantity"], 2)
            if price_lookup and p["code"] in price_lookup:
                price = price_lookup[p["code"]]
                row["current_price"] = price
                if p["cost"] > 0:
                    row["pnl_pct"] = round((price - p["cost"]) / p["cost"] * 100, 2)
                    row["pnl_amount"] = round((price - p["cost"]) * p["quantity"], 2)
            result.append(row)
        return result

    def compute_total_position_ratio(self, price_lookup: Optional[dict] = None) -> dict:
        """计算实际组合总仓位（持仓成本/市值 ÷ 总资产）。

        第 1 条：先算实际组合总仓位再给建议。总资产来自 portfolio.json
        顶层 `total_assets`（元）；未配置时返回 None + 提示，不猜测资金上下文。

        Args:
            price_lookup: {code: 现价} 字典，提供时额外算市值口径占比。

        Returns:
            {
                "total_assets": float|None,       # 配置的总资产（元）
                "position_cost": float,           # 持仓成本合计（元）
                "position_mv": float|None,        # 持仓市值合计（元，需 price_lookup）
                "position_ratio": float|None,     # 成本口径占比 %（缺 total_assets→None）
                "position_ratio_mv": float|None,  # 市值口径占比 %（可选）
                "warning": str|None,              # 缺 total_assets 或成本占比 >90% 提示
            }
        """
        rows = self.get_positions_with_pnl(price_lookup)
        position_cost = round(sum(float(p.get("cost_total", 0) or 0) for p in rows), 2)
        total_assets = self._data.get("total_assets")
        if not total_assets:
            return {
                "total_assets": None,
                "position_cost": position_cost,
                "position_mv": None,
                "position_ratio": None,
                "position_ratio_mv": None,
                "warning": "portfolio.json 未配置 total_assets（元），无法计算实际总仓位",
            }
        total_assets = float(total_assets)
        ratio_cost = round(position_cost / total_assets * 100, 2) if total_assets else 0.0
        position_mv = None
        ratio_mv = None
        if price_lookup and rows:
            mv_total = sum(float(p.get("current_price", 0) or 0) * float(p.get("quantity", 0) or 0) for p in rows)
            if mv_total:
                position_mv = round(mv_total, 2)
                ratio_mv = round(mv_total / total_assets * 100, 2)
        warning = None
        if ratio_cost > 90:
            warning = f"组合成本占总资产 {ratio_cost}%（>90%），仓位过重，建议保留现金缓冲"
        return {
            "total_assets": total_assets,
            "position_cost": position_cost,
            "position_mv": position_mv,
            "position_ratio": ratio_cost,
            "position_ratio_mv": ratio_mv,
            "warning": warning,
        }

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

    # ---------- 持仓操作（P2-P1 拆分：实现移至 portfolio.crud，此处 thin wrapper） ----------

    def add_position(
        self,
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

        cost_source 记录成本来源（user_input / screenshot / calculated），
        加仓产生加权平均成本时自动置为 calculated，保留可追溯性。
        """
        from portfolio.crud import add_position as _add

        return _add(
            self,
            code,
            name,
            cost,
            quantity,
            buy_date=buy_date,
            tags=tags,
            auto_save=auto_save,
            cost_source=cost_source,
        )

    def reduce_position(
        self, code: str, quantity: int, auto_save: bool = True, sell_price: float = None
    ) -> Optional[dict]:
        """减仓。返回减仓后的持仓信息，如果全部卖出则移除并记录交易日志。"""
        from portfolio.crud import reduce_position as _reduce

        return _reduce(self, code, quantity, auto_save=auto_save, sell_price=sell_price)

    def remove_position(self, code: str, auto_save: bool = True) -> bool:
        """清仓（移除持仓）并记录交易日志。"""
        from portfolio.crud import remove_position as _remove

        return _remove(self, code, auto_save=auto_save)

    def update_position(self, code: str, auto_save: bool = True, **kwargs) -> Optional[dict]:
        """更新持仓字段（cost, quantity, name, buy_date, tags, cost_source）。

        cost 变更时记录 cost_before/cost_after 到 oplog；显式更新 cost
        时若未提供 cost_source，默认标记为 user_input。
        """
        from portfolio.crud import update_position as _update

        return _update(self, code, auto_save=auto_save, **kwargs)

    def tag_position(self, code: str, *tags: str, auto_save: bool = True) -> Optional[dict]:
        """给持仓添加标签。"""
        from portfolio.crud import tag_position as _tag

        return _tag(self, code, *tags, auto_save=auto_save)

    def untag_position(self, code: str, *tags: str, auto_save: bool = True) -> Optional[dict]:
        """移除持仓标签。"""
        from portfolio.crud import untag_position as _untag

        return _untag(self, code, *tags, auto_save=auto_save)

    # ---------- 自选操作（P2-P1 拆分：实现移至 portfolio.crud，此处 thin wrapper） ----------

    def add_watch(
        self,
        code: str,
        name: str = "",
        target_buy: float = 0,
        target_sell: float = 0,
        auto_save: bool = True,
        _update_fields: tuple = (),
    ) -> dict:
        """添加自选股。_update_fields: 显式更新的字段名（update_watch 复用入口用）。"""
        from portfolio.crud import add_watch as _add_watch

        return _add_watch(
            self,
            code,
            name=name,
            target_buy=target_buy,
            target_sell=target_sell,
            auto_save=auto_save,
            _update_fields=_update_fields,
        )

    def remove_watch(self, code: str, auto_save: bool = True) -> bool:
        """移除自选股。"""
        from portfolio.crud import remove_watch as _remove_watch

        return _remove_watch(self, code, auto_save=auto_save)

    # ---------- 分析（v1.17.0 拆分预备：从 manager 抽到 portfolio.analytics） ----------

    def to_dict(self) -> dict:
        """返回完整数据浅副本（v1.16.0 thin wrapper → portfolio.analytics.to_dict）。"""
        from portfolio.analytics import to_dict as _to_dict

        return _to_dict(self)

    def summary(self) -> str:
        """返回持仓摘要文本（v1.16.0 thin wrapper → portfolio.analytics.summary）。"""
        from portfolio.analytics import summary as _summary

        return _summary(self)

    # ---------- 风险与归因（v1.16.0 thin wrapper → portfolio.analytics） ----------

    def risk_summary(self, quotes: dict = None, confidence: float = 0.95) -> str:
        """持仓组合 VaR 风险摘要（→ portfolio.analytics.risk_summary）。"""
        from portfolio.analytics import risk_summary as _risk_summary

        return _risk_summary(self, quotes=quotes, confidence=confidence)

    def attribution_report(self, quotes: dict = None, period: str = "1M") -> str:
        """组合 Brinson 归因报告（→ portfolio.analytics.attribution_report）。"""
        from portfolio.analytics import attribution_report as _attribution_report

        return _attribution_report(self, quotes=quotes, period=period)

    def advisory_rebalance(self, target_ratio: float = 1.0, quotes: dict = None) -> list:
        """调仓建议（→ portfolio.rebalance.advisory_rebalance）。"""
        from portfolio.rebalance import advisory_rebalance as _advisory_rebalance

        return _advisory_rebalance(self, target_ratio=target_ratio, quotes=quotes)

    # ---------- 导入导出 ----------

    def export_codes(self) -> list:
        """导出所有持仓代码列表（兼容旧接口）。"""
        return [p["code"] for p in self.get_positions()]

    # ---------- 健康检查（v1.21.2 拆分到 health_report.py） ----------

    def health_report(self, *args, **kwargs):
        """委托到 portfolio.health_report（v1.21.2 拆分）。"""
        from portfolio.health_report import health_report as _hr

        return _hr(self, *args, **kwargs)

    def health_report_markdown(self, report: dict) -> str:
        """委托到 portfolio.health_report（v1.21.2 拆分）。"""
        from portfolio.health_report import health_report_markdown as _hrm

        return _hrm(report)

    def check_concentration(self, *args, **kwargs):
        """委托到 portfolio.health_report（v1.21.2 拆分）。"""
        from portfolio.health_report import check_concentration as _cc

        return _cc(self, *args, **kwargs)
