"""全市场快照：提供自适应预筛选所需的市场水位数据 (#1)。

计算近 20 日全市场日均成交额与中位市值，供 pre_screen_quotes 动态调整门槛。
优先从 data/snapshots 缓存读取；缓存缺失时从当前 quote 批量计算。
"""

import logging
import statistics
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 缓存有效期（秒）：日内复用，避免每次预筛选都重新计算
_CACHE_TTL = 3600  # 1 小时


def _get_data_dir() -> Path:
    """获取数据目录（支持 monkeypatch）。"""
    from common.utils import DATA_DIR as _DATA_DIR

    return globals().get("DATA_DIR", _DATA_DIR)


def get_market_snapshot(days: int = 20) -> dict:
    """获取全市场水位快照。

    返回:
        {
            "avg_amount_yuan": float,  # 近 days 日全市场日均成交额（元）
            "median_cap": float,       # 全市场中位总市值（亿元）
            "updated": str,            # ISO 时间戳
            "source": str,             # "cache" | "computed"
        }
    """
    cached = _load_cache()
    if cached and _is_fresh(cached, _CACHE_TTL):
        return cached

    # 缓存缺失时从当前 quote 计算（仅当日截面，非 20 日均值，但有总比无好）
    snapshot = _compute_from_quotes()
    _save_cache(snapshot)
    return snapshot


def _load_cache() -> Optional[dict]:
    """从磁盘加载缓存。"""
    path = _get_data_dir() / "market_snapshot.json"
    if not path.exists():
        return None
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except Exception as e:
        logger.debug("market_snapshot 缓存读取失败: %s", e)
        return None


def _save_cache(snapshot: dict) -> None:
    """保存快照到磁盘。"""
    try:
        import json

        path = _get_data_dir() / "market_snapshot.json"
        path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        logger.debug("market_snapshot 缓存写入失败: %s", e)


def _is_fresh(snapshot: dict, ttl: int) -> bool:
    """检查缓存是否在有效期内。"""
    updated = snapshot.get("updated", "")
    if not updated:
        return False
    try:
        ts = datetime.fromisoformat(updated)
        age = (datetime.now() - ts).total_seconds()
        return age < ttl
    except (ValueError, TypeError):
        return False


def _compute_from_quotes() -> dict:
    """从当前 quote 批量计算市场水位。

    全市场 quote 通过 data.get_quotes 获取，取当日截面：
    - avg_amount_yuan = 所有股票当日成交额的中位数（避免少数巨量股拉偏均值）
    - median_cap = 所有股票总市值的中位数
    """
    result = {
        "avg_amount_yuan": 0.0,
        "median_cap": 0.0,
        "updated": datetime.now().isoformat(),
        "source": "computed",
    }
    try:
        from data import get_quotes
        from common import to_float
        from business.universe_loader import load_full_market_universe

        codes = load_full_market_universe()
        if not codes:
            return result

        quotes = get_quotes(codes)
        amounts = []
        caps = []
        for q in quotes:
            amt = to_float(q.to_dict().get("amount", 0)) if hasattr(q, "to_dict") else 0
            cap = (
                to_float(q.to_dict().get("total_cap", 0))
                if hasattr(q, "to_dict")
                else 0
            )
            if amt > 0:
                amounts.append(amt)
            if cap > 0:
                caps.append(cap)

        if amounts:
            # 用中位数而非均值，避免少数巨量股拉偏
            result["avg_amount_yuan"] = round(statistics.median(amounts), 0)
        if caps:
            result["median_cap"] = round(statistics.median(caps), 2)
    except Exception as e:
        logger.warning("market_snapshot 计算失败: %s", e)

    return result
