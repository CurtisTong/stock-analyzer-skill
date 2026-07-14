"""(#3) 涨停池数据入口：一次性拉取全市场涨停池并缓存。

复用 technical/sentiment.py 的 getTopicZTPool 接口，但暴露按股票维度的
封单/炸板/换手字段，供涨跌停过滤区分一字板与换手板。

全市场仅 +1 次 HTTP（O(1)），不影响预筛选性能。
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# 缓存有效期（秒）：日内复用
_CACHE_TTL = 300  # 5 分钟
_cache: dict = {}
_cache_ts: float = 0.0


def get_zt_pool(date: str = "") -> dict:
    """获取当日涨停池（按股票 code 索引）。

    Args:
        date: 日期 YYYYMMDD（空值取当日）

    Returns:
        {code: {lbc, zbc, fund_buy, turnover_rate, name, change_pct}}
        失败返回空 dict，调用方应回退绝对涨跌停过滤。
    """
    import time

    global _cache, _cache_ts

    # 缓存命中（仅当日数据）
    if not date and _cache and (time.time() - _cache_ts) < _CACHE_TTL:
        return _cache

    try:
        from technical.sentiment import _EASTMONEY_UT, _http_get_json
    except ImportError:
        logger.debug("sentiment 模块不可用，涨停池获取失败")
        return {}

    if not _EASTMONEY_UT:
        logger.debug("EASTMONEY_UT_TOKEN 未配置，跳过涨停池获取")
        return {}

    try:
        url = "https://push2ex.eastmoney.com/getTopicZTPool"
        params = {
            "ut": _EASTMONEY_UT,
            "dpt": "wz.ztzt",
            "date": date or datetime.now().strftime("%Y%m%d"),
        }
        data = _http_get_json(url, params=params)
        pool = data.get("data", {}).get("pool", [])

        result = {}
        for item in pool:
            # 东财代码格式 "600519" -> 标准化为 "sh600519"
            raw_code = str(item.get("c", ""))
            if not raw_code:
                continue
            code = _normalize_code(raw_code)
            result[code] = {
                "lbc": item.get("lbc", 0),            # 连板数
                "zbc": item.get("zbc", 0),            # 炸板次数
                "fund_buy": item.get("fund", 0),      # 封单资金（元）
                "turnover_rate": item.get("hs", 0),   # 换手率(%)
                "name": item.get("n", ""),
                "change_pct": item.get("zdp", 0),     # 涨跌幅
            }

        # 更新缓存（仅未指定日期时缓存当日数据）
        if not date:
            _cache = result
            _cache_ts = time.time()

        return result
    except Exception as e:
        logger.debug("涨停池获取失败: %s", e)
        return {}


def _normalize_code(raw_code: str) -> str:
    """将东财纯数字代码标准化为 sh/sz 前缀格式。"""
    if not raw_code.isdigit():
        return raw_code
    if raw_code.startswith("6"):
        return f"sh{raw_code}"
    elif raw_code.startswith("0") or raw_code.startswith("3"):
        return f"sz{raw_code}"
    elif raw_code.startswith("8") or raw_code.startswith("4"):
        return f"bj{raw_code}"
    return raw_code


def is_one_word_limit_up(code: str, zt_pool: dict = None) -> bool:
    """(#3) 判定是否为一字板（无量涨停）。

    一字板特征：封单资金大 + 炸板次数=0 + 换手率极低（<1%）
    一字板 T+1 无法买入，应硬过滤。

    Args:
        code: 标准化代码（如 sh600519）
        zt_pool: 涨停池 dict（None 时自动获取）

    Returns:
        True = 一字板（硬过滤），False = 换手板或非涨停（可参与）
    """
    if zt_pool is None:
        zt_pool = get_zt_pool()

    item = zt_pool.get(code)
    if not item:
        return False  # 不在涨停池 -> 非涨停，不判定为一字板

    zbc = item.get("zbc", 0)
    turnover = item.get("turnover_rate", 0)
    fund_buy = item.get("fund_buy", 0)

    # 一字板：未炸板 + 换手率极低（<1%）+ 有封单
    return zbc == 0 and turnover < 1.0 and fund_buy > 0


def clear_cache():
    """清除缓存（测试用）。"""
    global _cache, _cache_ts
    _cache = {}
    _cache_ts = 0.0
