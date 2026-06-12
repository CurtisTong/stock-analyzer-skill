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
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _now_iso() -> str:
    """获取当前时间的 ISO 格式字符串。"""
    return datetime.now().isoformat()

# v1.3.1: 缓存已迁入 common.cache，此处仅作兼容 shim（见 data.cache）
from common import cache


def _get_common_helpers():
    """延迟导入 common，避免 common.py ↔ data/__init__.py 循环导入。"""
    from common import to_float, to_int
    return to_float, to_int

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


def get_quote(code: str, use_cache: bool = True) -> Optional[Quote]:
    """获取单只股票行情。"""
    _load_fetchers()
    cfg = get_config()
    key = f"quote_{code}"

    if use_cache:
        cached = cache.get_json(key, cfg.quote_cache_ttl)
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
    cfg = get_config()
    results = parallel_map(lambda c: get_quote(c, use_cache), codes,
                           max_workers=cfg.max_workers, timeout=30)
    return [q for q in results.values() if q is not None]


def get_kline(code: str, scale: int = 240, datalen: int = 30,
              use_cache: bool = True) -> list:
    """获取 K 线数据。

    Args:
        code: 股票代码
        scale: K线周期（1/5/15/30/60/240/1440）
        datalen: 数据长度
        use_cache: 是否使用缓存
    """
    _load_fetchers()
    cfg = get_config()

    # 根据周期选择合适的 TTL
    if scale == 1:
        cache_ttl = cfg.kline_1m_cache_ttl
    elif scale == 240:
        cache_ttl = cfg.kline_240m_cache_ttl
    else:
        cache_ttl = cfg.kline_cache_ttl

    key = f"kline_{code}_{scale}_{datalen}"

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
    key = f"finance_{code}"

    if use_cache:
        cached = cache.get_json(key, cfg.finance_cache_ttl)
        if cached:
            records = [_dict_to_finance(r) for r in cached]
            # 校验缓存有效性：至少有一个非零数据点
            if any(r.eps != 0 or r.roe != 0 for r in records):
                return records
            # 零值缓存视为无效，忽略并重新拉取

    result = _finance_manager.fetch(code)
    if not result:
        return []

    records = [_dict_to_finance(r) for r in result]

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


def _dict_to_kline_bar(d: dict) -> KlineBar:
    to_float, to_int = _get_common_helpers()
    return KlineBar(
        day=d.get("day", ""),
        open=to_float(d.get("open")),
        high=to_float(d.get("high")),
        low=to_float(d.get("low")),
        close=to_float(d.get("close")),
        volume=to_int(d.get("volume")),
        amount=to_float(d.get("amount")),
        pct_chg=to_float(d.get("pct_chg")),
        source=d.get("source", ""),
        fetch_time=d.get("fetch_time") or _now_iso(),
    )


def _dict_to_finance(d: dict) -> FinanceRecord:
    """将 fetcher 返回的 dict 转为 FinanceRecord，支持东财原始字段名映射。"""
    to_float, _ = _get_common_helpers()
    FIELD_MAP = {
        "report_date": ["REPORT_DATE", "REPORTDATETIME", "NOTICE_DATE"],
        "eps": ["EPSJB"],
        "roe": ["ROEJQ"],
        "revenue_yoy": ["TOTALOPERATEREVETZ"],
        "net_profit_yoy": ["PARENTNETPROFITTZ"],
        "gross_margin": ["XSMLL"],
        "net_margin": ["XSJLL"],
        "debt_ratio": ["ZCFZL"],
        "bps": ["BPS"],
        "ocf_per_share": ["MGJYXJJE"],
    }

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
        source=d.get("source", ""),
        fetch_time=d.get("fetch_time") or _now_iso(),
    )
