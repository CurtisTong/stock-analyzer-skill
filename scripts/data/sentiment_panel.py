"""情绪面板数据层（v1.26 情绪因子的数据来源）。

职责：
1. 拉取东财 push2ex 的涨停池（`getTopicZTPool`）与炸板池（`getTopicZBPool`），
   聚合成每日快照（个股明细 + 板块分布 + 市场级计数）；
2. 落盘历史快照（`sentiment_snapshots.json`，保留最近 60 个交易日），
   供晋级率与板块 5 日轮动等**需要历史**的口径计算；
3. 提供按标的查询的只读接口（`get_stock_sentiment` / `get_sector_heat`）。

设计要点（见 docs/design/sentiment-factor-design.md）：
- 快照只读不写副作用：拉取与落盘是显式的两个动作（`refresh_panel` / `save_snapshot`），
  因子计算只读文件；
- 缺��语义严格：无法计算的字段留 `None`（不伪装成 0——0 会被读成"零晋级""零封单"）；
- 全市场口径只取 2 次 HTTP（涨停池 + 炸板池），与股票池规模无关。
"""

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 快照保留天数（交易日）——足够算 5 日 / 20 日轮动，文件大小可控
MAX_SNAPSHOT_DAYS = 60

# 涨停池/炸板池缓存（秒）：日内复用，避免因子逐股重复拉取
_CACHE_TTL = 300
_cache: dict = {}
_cache_ts: float = 0.0


def _snapshot_path() -> Path:
    """快照文件路径（scripts/data/sentiment_snapshots.json）。"""
    return Path(__file__).resolve().parent / "sentiment_snapshots.json"


# ──────────────────────────── 池数据拉取 ────────────────────────────


def _fetch_pool(endpoint: str, date: str) -> list[dict]:
    """拉取东财 push2ex 池数据（涨停/炸板）。

    Args:
        endpoint: "getTopicZTPool"（涨停）或 "getTopicZBPool"（炸板）
        date: YYYYMMDD

    Returns:
        原始 pool 列表；失败返回空列表
    """
    try:
        from technical.sentiment import MarketDataFetcher, _http_get_json

        ut = os.getenv("EASTMONEY_UT_TOKEN", "") or MarketDataFetcher._PUBLIC_UT
        url = f"https://push2ex.eastmoney.com/{endpoint}"
        params = {
            "ut": ut,
            "dpt": "wz.ztzt",
            "Pageindex": "0",
            "pagesize": "10000",
            "sort": "fbt:asc",
            "date": date,
        }
        data = _http_get_json(url, params=params)
        return (data.get("data") or {}).get("pool") or []
    except Exception as e:
        logger.debug("拉取 %s 失败: %s", endpoint, e)
        return []


def _normalize_code(raw_code: str) -> str:
    """东财纯数字代码 → sh/sz/bj 前缀格式。"""
    if not raw_code or not raw_code.isdigit():
        return raw_code
    if raw_code.startswith("6"):
        return f"sh{raw_code}"
    if raw_code.startswith("0") or raw_code.startswith("3"):
        return f"sz{raw_code}"
    if raw_code.startswith("8") or raw_code.startswith("4"):
        return f"bj{raw_code}"
    return raw_code


def _opt_float(value: object) -> Optional[float]:
    """可选浮点：空值/异常返回 None（区别于 0）。

    `common.utils.to_float` 的 default 标注为 float（传 None 虽能运行但
    不符合类型契约），这里用独立辅助保持 None 语义且不动公共 API。
    """
    if value is None or value == "" or value == "-":
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _pool_entry(item: dict, status: str) -> dict:
    """池条目 → 快照个股条目。

    字段缺失一律留 None（不填 0）：`fund` 缺失与"没有封单"是两件事，
    混淆会让缺失数据被当成封不住而扣分（实测约 1/4 样本 fund 缺失）。
    """
    raw_code = str(item.get("c", ""))
    lbc = _opt_float(item.get("lbc"))
    zbc = _opt_float(item.get("zbc"))
    return {
        "code": _normalize_code(raw_code),
        "name": item.get("n", ""),
        "status": status,  # limit_up / broken
        "lbc": int(lbc) if lbc is not None else None,
        "zbc": int(zbc) if zbc is not None else None,
        "fund": _opt_float(item.get("fund")),
        "ltsz": _opt_float(item.get("ltsz")),
        "hs": _opt_float(item.get("hs")),
        "zdp": _opt_float(item.get("zdp")),
        "sector": item.get("hybk") or "",
    }


def refresh_panel(date: str = "") -> Optional[dict]:
    """拉取涨停池 + 炸板池，聚合成当日情绪面板。

    Args:
        date: YYYYMMDD（空 = 当日）

    Returns:
        面板 dict；两个池都为空时返回 None（无法构造有效面板）
    """
    global _cache, _cache_ts

    if not date and _cache and (time.time() - _cache_ts) < _CACHE_TTL:
        return _cache

    if not date:
        from datetime import datetime

        date = datetime.now().strftime("%Y%m%d")

    limit_pool = _fetch_pool("getTopicZTPool", date)
    broken_pool = _fetch_pool("getTopicZBPool", date)
    if not limit_pool and not broken_pool:
        logger.debug("情绪面板：涨停池与炸板池均为空")
        return None

    stocks: dict = {}
    for item in limit_pool:
        entry = _pool_entry(item, "limit_up")
        if entry["code"]:
            stocks[entry["code"]] = entry
    for item in broken_pool:
        entry = _pool_entry(item, "broken")
        if entry["code"] and entry["code"] not in stocks:
            stocks[entry["code"]] = entry

    # 板块聚合（hybk = 行业板块）：按涨停/炸板家数分别计
    sectors: dict = {}
    for entry in stocks.values():
        sector = entry.get("sector") or ""
        if not sector:
            continue
        agg = sectors.setdefault(sector, {"limit_up": 0, "broken": 0})
        if entry["status"] == "limit_up":
            agg["limit_up"] += 1
        else:
            agg["broken"] += 1
    for agg in sectors.values():
        agg["count"] = agg["limit_up"] + agg["broken"]

    # 连板高度分布（仅涨停股有 lbc）
    height_distribution: dict = {}
    max_height = 0
    for entry in stocks.values():
        lbc = entry.get("lbc")
        if entry["status"] != "limit_up" or not lbc:
            continue
        height_distribution[str(lbc)] = height_distribution.get(str(lbc), 0) + 1
        max_height = max(max_height, lbc)

    limit_up_count = sum(1 for e in stocks.values() if e["status"] == "limit_up")
    broken_count = sum(1 for e in stocks.values() if e["status"] == "broken")

    chg_values = [e["zdp"] for e in stocks.values() if e.get("zdp") is not None]
    median_chg = None
    if chg_values:
        ordered = sorted(chg_values)
        mid = len(ordered) // 2
        median_chg = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2

    panel = {
        "date": date,
        "limit_up_count": limit_up_count,
        "broken_count": broken_count,
        "max_height": max_height,
        "height_distribution": height_distribution,
        "median_chg_pct": round(median_chg, 2) if median_chg is not None else None,
        "sectors": sectors,
        "stocks": stocks,
    }

    if not date:
        _cache = panel
        _cache_ts = time.time()
    return panel


# ──────────────────────────── 快照读写 ────────────────────────────


def load_snapshots() -> dict:
    """读取历史快照（损坏时视为空）。"""
    path = _snapshot_path()
    if not path.exists():
        return {"version": 1, "snapshots": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.debug("情绪快照读取失败: %s", e)
        return {"version": 1, "snapshots": {}}
    if not isinstance(data, dict):
        return {"version": 1, "snapshots": {}}
    data.setdefault("version", 1)
    data.setdefault("snapshots", {})
    return data


def save_snapshot(panel: dict) -> bool:
    """把面板写入历史快照（原子写），并滚动清理超出保留期的快照。

    Args:
        panel: refresh_panel() 的输出

    Returns:
        是否写入成功
    """
    if not panel or not panel.get("date"):
        return False
    data = load_snapshots()
    snapshots = data.setdefault("snapshots", {})
    snapshots[panel["date"]] = panel

    # 滚动清理：只保留最近 MAX_SNAPSHOT_DAYS 个交易日
    if len(snapshots) > MAX_SNAPSHOT_DAYS:
        for old in sorted(snapshots.keys())[: len(snapshots) - MAX_SNAPSHOT_DAYS]:
            snapshots.pop(old, None)

    path = _snapshot_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
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
    except OSError as e:
        logger.debug("情绪快照写入失败: %s", e)
        return False
    return True


def refresh_and_save(date: str = "") -> Optional[dict]:
    """拉取面板并落盘（显式写动作；因子计算不调用本函数）。"""
    panel = refresh_panel(date)
    if panel is None:
        return None
    save_snapshot(panel)
    return panel


def get_latest_snapshot() -> Optional[dict]:
    """最近一个交易日的快照（按日期倒序取第一个）。"""
    snapshots = load_snapshots().get("snapshots") or {}
    if not snapshots:
        return None
    latest_key = max(snapshots.keys())
    return snapshots[latest_key]


def get_snapshot(date: str) -> Optional[dict]:
    """取指定日期的快照（YYYYMMDD）。

    回测必须按**历史时点**取快照——用最新快照计算历史因子是未来函数。
    该日期无快照时返回 None（因子缺失）。
    """
    snapshots = load_snapshots().get("snapshots") or {}
    return snapshots.get(date)


def get_history(days: int = 5) -> list[dict]:
    """最近 N 个交易日的快照列表（按日期升序）。

    Args:
        days: 取最近几个交易日

    Returns:
        [快照, ...]（升序）；无历史时返回空列表
    """
    snapshots = load_snapshots().get("snapshots") or {}
    if not snapshots:
        return []
    keys = sorted(snapshots.keys())[-days:]
    return [snapshots[k] for k in keys]


# ──────────────────────────── 查询接口（只读） ────────────────────────────


def get_stock_sentiment(code: str, snapshot: Optional[dict] = None) -> Optional[dict]:
    """取某只股票在最新快照中的情绪条目。

    Args:
        code: 标准化代码（如 sh600519）
        snapshot: 指定快照（None = 最近一个）

    Returns:
        条目 dict；该股不在涨停/炸板池时返回 None（缺失，非 0 分）
    """
    if snapshot is None:
        snapshot = get_latest_snapshot()
    if not snapshot:
        return None
    code = _normalize_code(str(code))
    if not code.isdigit() and "_" not in code:
        # 传入裸代码时补前缀再查
        code = _normalize_code(code)
    return (snapshot.get("stocks") or {}).get(code)


def get_sector_heat(snapshot: Optional[dict] = None) -> dict:
    """取板块热度映射：板块 → 当日涨停家数占比（%）。"""
    if snapshot is None:
        snapshot = get_latest_snapshot()
    if not snapshot:
        return {}
    sectors = snapshot.get("sectors") or {}
    total = snapshot.get("limit_up_count") or 0
    if not total:
        return {}
    return {name: round((agg.get("limit_up", 0) / total) * 100, 2) for name, agg in sectors.items()}


def get_promotion_rate(snapshot: Optional[dict] = None) -> Optional[float]:
    """晋级率 = 昨日涨停股今日涨停的比例。

    Args:
        snapshot: 今日快照（None = 最近一个）

    Returns:
        晋级率 ∈ [0, 1]；昨日快照缺失时返回 None（历史不足，不可算）
    """
    if snapshot is None:
        snapshot = get_latest_snapshot()
    if not snapshot:
        return None
    date = snapshot.get("date", "")
    if not date:
        return None

    snapshots = load_snapshots().get("snapshots") or {}
    if len(snapshots) < 2:
        return None
    prev_keys = [k for k in sorted(snapshots.keys()) if k < date]
    if not prev_keys:
        return None

    prev = snapshots[prev_keys[-1]]
    prev_limit_up = {c for c, e in (prev.get("stocks") or {}).items() if e.get("status") == "limit_up"}
    if not prev_limit_up:
        return None
    today_limit_up = {c for c, e in (snapshot.get("stocks") or {}).items() if e.get("status") == "limit_up"}
    promoted = len(prev_limit_up & today_limit_up)
    return round(promoted / len(prev_limit_up), 4)


__all__ = [
    "MAX_SNAPSHOT_DAYS",
    "refresh_panel",
    "refresh_and_save",
    "load_snapshots",
    "save_snapshot",
    "get_latest_snapshot",
    "get_snapshot",
    "get_history",
    "get_stock_sentiment",
    "get_sector_heat",
    "get_promotion_rate",
]
