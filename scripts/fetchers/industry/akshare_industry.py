"""akshare 行业补全 fetcher（单只 60 天缓存）。

修复问题：quote.py 原本不返回 industry，所有 fetcher（tencent/akshare/eastmoney/sina）
行情接口均不带行业字段。本 fetcher 调用 akshare.stock_individual_info_em() 单只异步
补全，公司主营基本不变因此使用 60 天长缓存。失败时静默回退空字符串，由下游
classifier.infer_industry 走 keyword 推断兜底。
"""

from __future__ import annotations

from typing import Optional

import logging
from common.cache import cache_key_for_stock, get_json, set_json

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60 * 86400  # 60 天


def fetch_industry(code: str) -> str:
    """获取单只股票的行业字段。

    Returns:
        行业名称字符串；失败/缺失时返回空串。
    """
    code = _normalize(code)
    if not code:
        return ""

    key = cache_key_for_stock("industry", code)
    cached = get_json(key, CACHE_TTL_SECONDS)
    if isinstance(cached, dict):
        return cached.get("industry", "") or ""
    if isinstance(cached, str):
        # 兼容旧版本可能直接存字符串
        return cached

    try:
        industry = _fetch_from_akshare(code)
    except Exception as e:  # noqa: BLE001 — 网络异常统一兜底
        logger.debug("industry fetch failed for %s: %s", code, e)
        industry = ""

    # 写缓存（即使为空也写，避免短期内重复请求失败端点）
    set_json(key, {"industry": industry})
    return industry


def _fetch_from_akshare(code: str) -> str:
    """调用 akshare 拉取单只股票行业字段。"""
    import akshare as ak  # 延迟导入，未安装时不影响主链路

    symbol = _to_akshare_symbol(code)
    df = ak.stock_individual_info_em(symbol=symbol)
    # DataFrame 列：item / value；找 item == "行业"
    if df is None or df.empty:
        return ""
    rows = df[df["item"] == "行业"]
    if rows.empty:
        return ""
    value = rows["value"].iloc[0]
    return str(value).strip() if value else ""


def _normalize(code: str) -> str:
    """统一代码格式：去前缀/去空格。"""
    if not code:
        return ""
    code = code.strip().lower()
    # 去掉 sh/sz/bj 前缀
    if code.startswith(("sh", "sz", "bj")) and len(code) > 6:
        code = code[2:]
    return code


def _to_akshare_symbol(code: str) -> str:
    """akshare.stock_individual_info_em 需要 6 位纯数字代码。"""
    code = _normalize(code)
    # 去除可能存在的 .SH/.SZ 等后缀
    if "." in code:
        code = code.split(".")[0]
    return code
