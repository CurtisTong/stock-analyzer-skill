"""
数据获取便捷函数，封装常见的获取+转换模式。

消除 screener.py、long_term.py、alert_engine.py 等文件中重复的适配代码。
"""

from __future__ import annotations

import logging
from typing import Optional

from common import get_shared_executor
from common.exceptions import (
    DataError,
    NetworkError,
    ParseError,
)
from data import get_quote, get_quotes, get_kline, get_finance
from data.types import FinanceMeta

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
    """获取财务数据，返回 dict 列表。

    WP4: get_finance 返回 (records, meta) tuple，本函数保持只返回 dict 列表
    （向后兼容）。若需 meta，使用 fetch_finance_first_with_meta。
    """
    records, _meta = get_finance(code)
    return [r.to_dict() for r in records]


def fetch_finance_first(code: str) -> dict:
    """获取财务数据，返回第一条 dict（无数据返回空 dict）。

    WP4: 内部解构 (records, meta) tuple，丢弃 meta，保持返回 dict 的旧 API。
    """
    records, _meta = get_finance(code)
    return records[0].to_dict() if records else {}


def fetch_finance_first_with_meta(code: str) -> tuple[dict, FinanceMeta]:
    """获取财务数据 + meta（WP4 新增）。

    Returns:
        (finance_dict, meta) 元组
    """
    records, meta = get_finance(code)
    finance_dict = records[0].to_dict() if records else {}
    if not isinstance(meta, FinanceMeta):
        meta = FinanceMeta()
    return finance_dict, meta


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

    WP4: 内部解构 get_finance 的 (records, meta) tuple，仅返回 records 列表。
    """
    from concurrent.futures import as_completed
    from common import normalize_finance_code

    results = {}

    def _fetch_one(code):
        records, _meta = get_finance(normalize_finance_code(code))
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


# ---------- 报告期口径工具（2026-07-23 宝丰能源 PE 误算复盘） ----------
# 单季 EPS 不可直接做 price/eps；累计期不可直接算 PE（需 TTM）。
# 这两个纯函数供业务层/渲染层在算 PE 前校验口径，避免高估 PE（如 47 倍）。


def expected_period_type(report_date: str) -> str:
    """按 report_date 末尾日期推断预期 period_type（兜底，不替代东财 REPORT_TYPE）。

    优先使用 FinanceRecord.period_type（东财 REPORT_TYPE 归一化值）；
    仅在 period_type 为空（akshare 不返回）时用本函数兜底推断。

    Args:
        report_date: 报告期日期，如 "2025-03-31"

    Returns:
        "annual" / "cumulative" / "quarterly" / ""
    """
    if report_date.endswith("-12-31"):
        return "annual"
    if report_date.endswith("-03-31"):
        return "quarterly"
    if report_date.endswith(("-06-30", "-09-30")):
        return "cumulative"
    return ""


def compute_pe(price: float, eps, period_type: str) -> dict:
    """根据 EPS 口径自动选 PE 算法。

    Args:
        price: 当前股价
        eps: 每股收益（可能为 None / 0）
        period_type: "annual" / "cumulative" / "quarterly" / ""

    Returns:
        {"pe": float|None, "method": str}
        - annual: 直接 price/eps
        - quarterly: 单季年化 price/(eps*4)，标记"近似"
        - cumulative: 不可直接算，返回 None 提示需 TTM
        - 空/None/0 eps: 返回 None
    """
    if eps is None or eps == 0 or price <= 0:
        return {"pe": None, "method": "数据不足"}
    if period_type == "annual":
        return {"pe": round(price / eps, 2), "method": "PE(年报)"}
    if period_type == "quarterly":
        annualized = eps * 4
        return {
            "pe": round(price / annualized, 2),
            "method": f"PE(单季×4={annualized:.2f}年化,近似)",
        }
    if period_type == "cumulative":
        return {"pe": None, "method": "累计期不可直接算PE,需配TTM"}
    return {"pe": None, "method": "口径未知"}
