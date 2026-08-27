"""板块动量工具（v1.21.0 ）：基于行业 ETF 动量判断板块退潮。

用于 screener 板块退潮过滤：个股所属行业（infer_industry 输出）近似映射到
sector_etf.csv 中的行业 ETF，若该 ETF 近 5 日跌幅超过阈值（默认 5%），
判定板块退潮，可配合 --exclude-sector-momentum 剔除，或对高分标的加
sector_momentum_warning 标记。

注意：行业映射为近似映射，仅覆盖有行业 ETF 的类别；未覆盖行业不标记。
数据拉取失败时静默降级为空 dict，不阻塞 screener 主流程。
"""

from __future__ import annotations

import threading

# infer_industry 类别 -> sector_etf.csv 行业 ETF（近似映射，仅覆盖有 ETF 的行业）
_INDUSTRY_TO_ETF = {
    "医药": "sh512010",  # 医药ETF
    "半导体": "sh512480",  # 半导体ETF
    "银行": "sh512800",  # 银行ETF
    "基础化工": "sh516020",  # 化工ETF华宝
    "周期": "sh516020",  # 周期大类回退化工 ETF（化工权重大）
    "能源": "sh515220",  # 煤炭ETF国泰（能源中煤炭权重大）
    "军工": "sh512660",  # 军工ETF
    "制造": "sh516160",  # 新能源ETF（制造中含新能源/电池/光伏/汽车）
    "消费": "sh512690",  # 白酒ETF（消费中白酒权重大）
}

# 近 N 日动量判断窗口
DEFAULT_DAYS = 5
# 板块退潮阈值：N 日动量低于该值（%）判定退潮
SECTOR_WEAK_THRESHOLD = -5.0

_lock = threading.Lock()
_cache: dict = {}


def industry_etf_code(industry: str) -> str | None:
    """返回行业类别对应的 ETF 代码，无映射返回 None。"""
    return _INDUSTRY_TO_ETF.get(industry)


def _etf_ret(etf_code: str, days: int) -> float | None:
    """计算 ETF 近 days 日涨跌幅（%）。拉取失败返回 None。"""
    from common import normalize_quote_code
    from data import get_kline

    try:
        bars = get_kline(normalize_quote_code(etf_code), scale=240, datalen=days + 1)
        if not bars or len(bars) < 2:
            return None
        first = bars[0].get("close")
        last = bars[-1].get("close")
        if not first or not last:
            return None
        return (last / first - 1) * 100
    except Exception:
        return None


def fetch_sector_momentum(days: int = DEFAULT_DAYS) -> dict:
    """拉取所有已映射行业 ETF 的 N 日动量。

    Returns:
        {industry: {"etf": etf_code, "ret_{days}d": pct, "days": days}}，
        模块级缓存避免多策略重复拉取。全部失败时返回空 dict。
    """
    with _lock:
        if days in _cache:
            return _cache[days]

    etf_industries: dict = {}
    for industry, etf in _INDUSTRY_TO_ETF.items():
        etf_industries.setdefault(etf, []).append(industry)

    result = {}
    for etf, industries in etf_industries.items():
        ret = _etf_ret(etf, days)
        if ret is None:
            continue
        for industry in industries:
            # 标签带 days（修复固定 ret_5d 标签在 days≠5 时的错位）；days=5 时
            # 键名 ret_5d 不变，下游 screening_pipeline 兼容
            result[industry] = {
                "etf": etf,
                f"ret_{days}d": round(ret, 2),
                "days": days,
            }

    with _lock:
        _cache[days] = result
    return result


def clear_cache() -> None:
    """清空模块级缓存（测试用）。"""
    global _cache
    with _lock:
        _cache = {}
