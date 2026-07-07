"""
统一数据获取 API。

用法:
    from data import get_quote, get_kline, get_finance

    quote = get_quote("sh600989")
    quotes = get_quotes(["sh600989", "sz000807"])
    bars = get_kline("sh600989", scale=240, datalen=30)
    records = get_finance("SH600989")
"""

import threading
from typing import Optional
from datetime import datetime

from .types import Quote, KlineBar, FinanceRecord
from .config import get_config


def _now_iso() -> str:
    """获取当前时间的 ISO 格式字符串。"""
    return datetime.now().isoformat()


# v1.3.1: 缓存已迁入 common.cache，此处仅作兼容 shim（见 data.cache）
from common import cache


_helpers_cache = None


def _get_common_helpers():
    """延迟导入 common，避免 common.py ↔ data/__init__.py 循环导入。

    首次调用后缓存到模块级 _helpers_cache，后续直接返回。
    """
    global _helpers_cache
    if _helpers_cache is None:
        from common import to_float, to_int

        _helpers_cache = (to_float, to_int)
    return _helpers_cache


# 延迟导入 fetchers（避免循环导入），线程安全
_fetchers_lock = threading.Lock()
_fetchers_loaded = False
_quote_manager = None
_kline_manager = None
_finance_manager = None


def _load_fetchers():
    global _fetchers_loaded, _quote_manager, _kline_manager, _finance_manager
    if _fetchers_loaded:
        return
    with _fetchers_lock:
        if _fetchers_loaded:
            return
        from fetchers import get_quote_manager, get_kline_manager, get_finance_manager

        _quote_manager = get_quote_manager()
        _kline_manager = get_kline_manager()
        _finance_manager = get_finance_manager()
        _fetchers_loaded = True


def _reset_fetchers():
    """重置 fetcher 全局状态（仅用于测试隔离）。

    清空已加载的 manager 单例，使下次 get_quote/get_kline/get_finance
    调用重新触发 _load_fetchers，便于单元测试在干净状态下运行。
    """
    global _fetchers_loaded, _quote_manager, _kline_manager, _finance_manager
    with _fetchers_lock:
        _fetchers_loaded = False
        _quote_manager = None
        _kline_manager = None
        _finance_manager = None


def get_quote(code: str, use_cache: bool = True) -> Optional[Quote]:
    """获取单只股票行情。"""
    _load_fetchers()
    get_config()
    from common import normalize_quote_code

    code = normalize_quote_code(code)  # 归一化缓存键，避免 SH/sh/无前缀产生多份缓存
    key = cache.cache_key_for_stock("quote", code)

    if use_cache:
        from .config import get_quote_cache_ttl

        cached = cache.get_json(key, get_quote_cache_ttl())
        if cached:
            return _dict_to_quote(cached)

    result = _quote_manager.fetch(code)
    if result is None:
        return None

    quote = _dict_to_quote(result)

    if use_cache and quote.has_basic_data():
        cache.set_json(key, quote.to_dict())

    return quote


def get_quotes(codes: list, use_cache: bool = True) -> list:
    """批量获取行情。"""
    from common import parallel_map

    results = parallel_map(lambda c: get_quote(c, use_cache), codes, timeout=30)
    return [q for q in results.values() if q is not None]


def get_kline(
    code: str, scale: int = 240, datalen: int = 30, use_cache: bool = True
) -> list:
    """获取 K 线数据。

    Args:
        code: 股票代码
        scale: K线周期（1/5/15/30/60/240/1440）
        datalen: 数据长度
        use_cache: 是否使用缓存
    """
    _load_fetchers()
    cfg = get_config()
    from common import normalize_quote_code

    code = normalize_quote_code(code)  # 归一化缓存键

    # 根据周期选择合适的 TTL
    if scale == 1:
        cache_ttl = cfg.kline_1m_cache_ttl
    elif scale == 240:
        cache_ttl = cfg.kline_240m_cache_ttl
    else:
        cache_ttl = cfg.kline_cache_ttl

    key = cache.cache_key_for_stock("kline", code, scale=scale, datalen=datalen)

    if use_cache:
        cached = cache.get_json(key, cache_ttl)
        if cached:
            return [_dict_to_kline_bar(bar) for bar in cached]

    records = _kline_manager.fetch(code, scale=scale, datalen=datalen)
    if not records:
        return []

    bars = [_dict_to_kline_bar(r) for r in records]

    if use_cache and bars:
        cache.set_json(key, [b.to_dict() for b in bars])

    return bars


def get_finance(code: str, use_cache: bool = True) -> list:
    """获取财务数据。"""
    _load_fetchers()
    cfg = get_config()
    from common import normalize_finance_code

    code = normalize_finance_code(code)  # 归一化缓存键（东财大写前缀）
    key = cache.cache_key_for_stock("finance", code)
    zero_key = f"{key}_zero"

    if use_cache:
        cached = cache.get_json(key, cfg.finance_cache_ttl)
        if cached:
            records = [_dict_to_finance(r) for r in cached]
            # 校验缓存有效性：至少有一个非零数据点
            if any(r.eps != 0 or r.roe != 0 for r in records):
                return records
            # 零值缓存：可能是新股无数据或字段映射失败
            # 使用短 TTL 缓存避免重复网络请求
            zero_cached = cache.get_json(zero_key, 300)  # 5 分钟短缓存
            if zero_cached:
                return [_dict_to_finance(r) for r in zero_cached]

    result = _finance_manager.fetch(code)
    if not result:
        # P0-4: fetch 返回空也写 zero_key，避免对无数据股票的缓存穿透
        if use_cache:
            cache.set_json(zero_key, [])
        return []

    records = [_dict_to_finance(r) for r in result]

    # 完整性校验：所有记录 eps==0 且 roe==0 可能是字段映射失败或新股无数据
    # 使用短 TTL 缓存避免重复网络请求
    if records and all(r.eps == 0 and r.roe == 0 for r in records):
        if use_cache:
            cache.set_json(zero_key, [r.to_dict() for r in records])
        return records

    if use_cache and records:
        cache.set_json(key, [r.to_dict() for r in records])

    return records


# ---------- 内部转换函数（使用 common.to_float / common.to_int） ----------


def _dict_to_quote(d: dict) -> Quote:
    to_float, to_int = _get_common_helpers()
    return Quote(
        code=d.get("code", ""),
        name=d.get("name", ""),
        price=to_float(d.get("price")),
        prev_close=to_float(d.get("prev_close")),
        open=to_float(d.get("open")),
        high=to_float(d.get("high")),
        low=to_float(d.get("low")),
        change_pct=to_float(d.get("change_pct")),
        change_amt=to_float(d.get("change_amt")),
        volume=to_int(d.get("volume")),
        amount=to_float(d.get("amount")),
        turnover=to_float(d.get("turnover")),
        pe=to_float(d.get("pe")),
        pb=to_float(d.get("pb")),
        total_cap=to_float(d.get("total_cap")),
        circulating_cap=to_float(d.get("circulating_cap")),
        source=d.get("source", ""),
        fetch_time=d.get("fetch_time") or _now_iso(),
    )


def _normalize_volume(raw_volume: int, source: str) -> int:
    """将 volume 统一归一化为"股"。

    委托给 common.normalize_volume，保持单一真相源。
    """
    from common import normalize_volume

    return normalize_volume(raw_volume, source)


def _dict_to_kline_bar(d: dict) -> KlineBar:
    to_float, to_int = _get_common_helpers()
    source = d.get("source", "")
    raw_volume = to_int(d.get("volume"))
    return KlineBar(
        day=d.get("day", ""),
        open=to_float(d.get("open")),
        high=to_float(d.get("high")),
        low=to_float(d.get("low")),
        close=to_float(d.get("close")),
        volume=_normalize_volume(raw_volume, source),
        amount=to_float(d.get("amount")),
        pct_chg=to_float(d.get("pct_chg")),
        source=source,
        fetch_time=d.get("fetch_time") or _now_iso(),
    )


# 财务字段映射表（模块级常量，避免每次调用重建）
_FINANCE_FIELD_MAP = {
    "report_date": [
        "REPORT_DATE",
        "REPORTDATETIME",
        "NOTICE_DATE",
        "报告日期",
        "截止日期",
        "report_date",
    ],
    "eps": ["EPSJB", "基本每股收益", "每股收益", "eps"],
    "roe": ["ROEJQ", "净资产收益率", "加权净资产收益率", "ROE", "roe"],
    "revenue_yoy": [
        "TOTALOPERATEREVETZ",
        "营业收入同比",
        "营收同比",
        "营业总收入同比增长率",
        "营收同比(%)",
        "revenue_yoy",
    ],
    "net_profit_yoy": [
        "PARENTNETPROFITTZ",
        "归母净利润同比",
        "净利润同比",
        "归母净利润同比增长率",
        "净利润同比(%)",
        "net_profit_yoy",
    ],
    "gross_margin": [
        "XSMLL",
        "销售毛利率",
        "毛利率",
        "毛利率(%)",
        "销售毛利率(%)",
        "gross_margin",
    ],
    "net_margin": [
        "XSJLL",
        "销售净利率",
        "净利率",
        "净利率(%)",
        "销售净利率(%)",
        "net_margin",
    ],
    "debt_ratio": ["ZCFZL", "资产负债率", "资产负债率(%)", "debt_ratio"],
    "bps": ["BPS", "每股净资产", "bps"],
    "ocf_per_share": [
        "MGJYXJJE",
        "每股经营现金流",
        "每股现金流量净额",
        "ocf_per_share",
    ],
    # 商誉/质押字段：东财资产负债表和质押 API 可提供
    "goodwill": ["GOODWILL", "商誉", "商誉(元)", "goodwill"],
    "pledge_ratio": ["PLEDGE_RATIO", "质押比例", "股权质押比例", "pledge_ratio"],
    "goodwill_ratio": ["GOODWILL_RATIO", "商誉占比", "商誉/总资产", "goodwill_ratio"],
    # ESG/分红/治理字段
    "dividend_yield": ["DIVIDENT_YIELD", "股息率", "DY", "dividend_yield"],
    "consecutive_dividend_years": [
        "CONSECUTIVE_DIVIDEND_YEARS",
        "连续分红年数",
        "LXFHNX",
        "consecutive_dividend_years",
    ],
    "major_shareholder_reduction": [
        "MAJOR_SHAREHOLDER_REDUCTION",
        "大股东减持比例",
        "DSGJCP",
        "major_shareholder_reduction",
    ],
    "violation_penalty": [
        "VIOLATION_PENALTY",
        "违规处罚金额",
        "WGCFJE",
        "violation_penalty",
    ],
    "audit_opinion": [
        "AUDIT_OPINION",
        "审计意见类型",
        "SJYJ",
        "OPINION_TYPE",
        "audit_opinion",
    ],
}


def _dict_to_finance(d: dict) -> FinanceRecord:
    """将 fetcher 返回的 dict 转为 FinanceRecord，支持东财原始字段名映射。"""
    to_float, to_int = _get_common_helpers()
    FIELD_MAP = _FINANCE_FIELD_MAP

    def _find(candidates, default=""):
        for k in candidates:
            if k in d and d[k] not in (None, "", "-"):
                return d[k]
        return default

    return FinanceRecord(
        report_date=str(_find(FIELD_MAP["report_date"]))[:10],
        eps=to_float(_find(FIELD_MAP["eps"])),
        roe=to_float(_find(FIELD_MAP["roe"])),
        revenue_yoy=to_float(_find(FIELD_MAP["revenue_yoy"])),
        net_profit_yoy=to_float(_find(FIELD_MAP["net_profit_yoy"])),
        gross_margin=to_float(_find(FIELD_MAP["gross_margin"])),
        net_margin=to_float(_find(FIELD_MAP["net_margin"])),
        debt_ratio=to_float(_find(FIELD_MAP["debt_ratio"])),
        bps=to_float(_find(FIELD_MAP["bps"])),
        ocf_per_share=to_float(_find(FIELD_MAP["ocf_per_share"])),
        dividend_yield=to_float(_find(FIELD_MAP["dividend_yield"])),
        consecutive_dividend_years=to_int(
            _find(FIELD_MAP["consecutive_dividend_years"])
        ),
        major_shareholder_reduction=to_float(
            _find(FIELD_MAP["major_shareholder_reduction"])
        ),
        violation_penalty=to_float(_find(FIELD_MAP["violation_penalty"])),
        audit_opinion=str(_find(FIELD_MAP["audit_opinion"])),
        source=d.get("source", ""),
        fetch_time=d.get("fetch_time") or _now_iso(),
    )


# ---------- chip / event / flow / lhb 域统一入口 re-export ----------
# 这 4 个域的 fetcher 返回不同子类型数据，不走 DataFetcherManager 故障转移，
# 而是各自在 data/chip.py、data/event.py、data/flow.py、data/lhb.py 中
# 遍历 fetcher 列表按子类型聚合。这里 re-export 保持与 quote/kline/finance 一致的 API 风格。

def get_chip(code: str, days: int = 20) -> dict:
    """获取指定股票的资金面汇总数据（融资融券 + 股东户数 + 十大流通股东）。

    Args:
        code: 股票代码
        days: 融资融券获取天数（默认 20）

    Returns:
        {"margin": [...], "holders": [...], "top_holders": [...],
         "margin_summary": dict, "holders_summary": dict}
    """
    from data.chip import get_margin, get_holders, get_top_holders, get_margin_summary, get_holders_summary

    return {
        "margin": get_margin(code, days=days),
        "holders": get_holders(code),
        "top_holders": get_top_holders(code),
        "margin_summary": get_margin_summary(code, days=days),
        "holders_summary": get_holders_summary(code),
    }


def get_events(code: str, days: int = 30) -> dict:
    """获取指定股票的近期事件（财报/解禁/分红/增减持/违规）。"""
    from data.event import get_events as _get_events

    return _get_events(code, days)


def get_northbound_flow(code: str, days: int = 20) -> list:
    """获取北向资金近期数据（按日期升序）。"""
    from data.flow import get_northbound_flow as _get_nb

    return _get_nb(code, days=days)


# ---------- lhb 域统一入口 re-export ----------
from data.lhb import get_lhb_detail, get_lhb_seats  # noqa: E402, F401


__all__ = [
    "Quote",
    "KlineBar",
    "FinanceRecord",
    "get_quote",
    "get_quotes",
    "get_kline",
    "get_finance",
    "get_chip",
    "get_events",
    "get_northbound_flow",
    "get_lhb_detail",
    "get_lhb_seats",
]

