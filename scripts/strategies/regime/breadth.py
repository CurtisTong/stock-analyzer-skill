"""成分股均线宽度：CSI300 成分股站上 20 日均线比例。

替代原"指数阳线占比"，捕捉指数-个股背离（指数涨但个股跌的虚假繁荣）。
成分股 kline 有 1 小时磁盘缓存，冷缓存 ~15s（50 只样本）。

降级策略：成分股数据不可用时返回 None，调用方回退到原指数阳线占比。
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

from data import get_kline
from technical.core import sma

logger = logging.getLogger(__name__)

_CSI300_FILE = (
    Path(__file__).resolve().parent.parent.parent / "data" / "csi300_stocks.json"
)
_csi300_cache: Optional[list] = None
_breadth_cache: Optional[float] = None
_breadth_cache_ts: float = 0
_BREADTH_CACHE_TTL = 3600  # 1 小时内存缓存


def _load_csi300() -> list:
    """加载 CSI300 成分股列表（带内存缓存）。"""
    global _csi300_cache
    if _csi300_cache is not None:
        return _csi300_cache
    try:
        data = json.loads(_CSI300_FILE.read_text(encoding="utf-8"))
        _csi300_cache = data.get("constituents", [])
    except Exception as e:
        logger.debug("CSI300 成分股加载失败: %s", e)
        _csi300_cache = []
    return _csi300_cache


def compute_constituent_breadth(window: int = 20) -> Optional[float]:
    """返回成分股站上 MA20 的比例（0-1），失败返回 None。

    带 1 小时内存缓存，避免每次 regime 检测都拉成分股 kline。

    Args:
        window: 均线窗口（默认 20 日）

    Returns:
        站上 MA20 的比例（如 0.62 表示 62% 成分股在 MA20 之上），
        成分股列表为空或数据不可用时返回 None
    """
    global _breadth_cache, _breadth_cache_ts

    # 内存缓存检查
    now = time.time()
    if _breadth_cache is not None and (now - _breadth_cache_ts) < _BREADTH_CACHE_TTL:
        return _breadth_cache

    codes = _load_csi300()
    if not codes:
        return None

    above_count = 0
    total = 0
    for code in codes:
        try:
            bars = get_kline(code, scale=240, datalen=window + 1)
            if not bars or len(bars) < window + 1:
                continue
            closes = [b.close for b in bars if b.close > 0]
            if len(closes) < window + 1:
                continue
            ma20 = sma(closes, window)
            if ma20 is not None and closes[-1] > ma20:
                above_count += 1
            total += 1
        except Exception:
            continue

    if total == 0:
        return None

    result = above_count / total
    _breadth_cache = result
    _breadth_cache_ts = now
    return result


def reset_breadth_cache():
    """重置 breadth 内存缓存（测试用）。"""
    global _breadth_cache, _breadth_cache_ts
    _breadth_cache = None
    _breadth_cache_ts = 0
