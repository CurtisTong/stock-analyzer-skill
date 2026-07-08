"""
数据获取便捷函数，封装常见的获取+转换模式。

消除 screener.py、long_term.py、alert_engine.py 等文件中重复的适配代码。
"""

import logging
from typing import Optional

from common import get_shared_executor
from common.exceptions import (
    DataError,
    NetworkError,
    ParseError,
)
from data import get_quote, get_quotes, get_kline, get_finance

logger = logging.getLogger(__name__)


def fetch_quote_dict(code: str) -> dict:
    """获取单只行情，返回 dict（兼容旧接口）。"""
    q = get_quote(code)
    return q.to_dict() if q else {}


def fetch_quote_dict_or_none(code: str) -> Optional[dict]:
    """获取单只行情，返回 dict 或 None。"""
    q = get_quote(code)
    return q.to_dict() if q else None


def fetch_batch_dicts(codes: list) -> list:
    """批量获取行情，返回 dict 列表。"""
    quotes = get_quotes(codes)
    return [q.to_dict() for q in quotes]


def fetch_kline_dicts(code: str, scale: int = 240, datalen: int = 120) -> list:
    """获取 K 线，返回 dict 列表。"""
    bars = get_kline(code, scale=scale, datalen=datalen)
    return [b.to_dict() for b in bars]


def fetch_finance_dicts(code: str) -> list:
    """获取财务数据，返回 dict 列表。"""
    records = get_finance(code)
    return [r.to_dict() for r in records]


def fetch_finance_first(code: str) -> dict:
    """获取财务数据，返回第一条 dict（无数据返回空 dict）。"""
    records = get_finance(code)
    return records[0].to_dict() if records else {}


def fetch_stock_bundle(code: str, kline_scale: int = 240, kline_len: int = 120) -> dict:
    """一次性获取股票完整数据包（并行）。

    Returns:
        {"quote": dict|None, "kline": [dict], "finance": [dict]}
    """
    ex = get_shared_executor()
    f_q = ex.submit(fetch_quote_dict_or_none, code)
    f_k = ex.submit(fetch_kline_dicts, code, kline_scale, kline_len)
    f_f = ex.submit(fetch_finance_dicts, code)

    result = {"quote": None, "kline": [], "finance": []}
    try:
        result["quote"] = f_q.result(timeout=30)
    except (
        TimeoutError,
        ConnectionError,
        OSError,
        DataError,
        NetworkError,
        ParseError,
    ) as e:
        logger.warning("获取行情失败 %s: %s", code, e)
    try:
        result["kline"] = f_k.result(timeout=30)
    except (
        TimeoutError,
        ConnectionError,
        OSError,
        DataError,
        NetworkError,
        ParseError,
    ) as e:
        logger.warning("获取K线失败 %s: %s", code, e)
    try:
        result["finance"] = f_f.result(timeout=30)
    except (
        TimeoutError,
        ConnectionError,
        OSError,
        DataError,
        NetworkError,
        ParseError,
    ) as e:
        logger.warning("获取财务数据失败 %s: %s", code, e)
    return result


def prefetch_finance_all(codes: list) -> dict:
    """并发拉取所有股票的财务数据。

    Returns:
        {code: [finance_dict, ...]} 映射
    """
    from concurrent.futures import as_completed
    from common import normalize_finance_code

    results = {}

    def _fetch_one(code):
        records = get_finance(normalize_finance_code(code))
        return code, [r.to_dict() for r in records]

    ex = get_shared_executor()
    futures = {ex.submit(_fetch_one, c): c for c in codes}
    for future in as_completed(futures):
        try:
            code, data = future.result()
            results[code] = data
        except Exception:
            results[futures[future]] = []
    return results


def prefetch_kline_all(codes: list, scale: int = 240, datalen: int = 240) -> dict:
    """批量预拉 K 线（并行）。

    Returns:
        {code: [KlineBar, ...]} 映射
    """
    from common import parallel_fetch_dict, normalize_quote_code
    from data import get_kline as _get_kline  # 函数内导入支持 monkeypatch

    def _fetch_one(code):
        return _get_kline(normalize_quote_code(code), scale=scale, datalen=datalen)

    return parallel_fetch_dict(codes, _fetch_one, label="screener:kline")
