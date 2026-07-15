"""
数据源集合：自动发现并加载可用的数据源。
依赖包未安装时自动跳过对应数据源。

v1.3.2 起按数据域分组（7 个数据域 × 27 个 fetcher 模块 / 35 个 fetcher 类），
便于扩展时定位代码。子目录化后通过 __init__.py re-export 屏蔽 import 路径变更。

数据域分块：
  quote   - 实时行情        （10 个模块：tencent/eastmoney/sina/xueqiu/ths/efinance/akshare/tushare/pytdx/yfinance）
  kline   - K 线            （9 个模块：sina/eastmoney/tencent/efinance/akshare/tushare/baostock/pytdx/yfinance）
  finance - 财务            （2 个模块：eastmoney/akshare）
  flow    - 资金流向        （2 个模块：eastmoney/sina，3 个 fetcher 类）
  lhb     - 龙虎榜          （1 个模块：eastmoney，2 个 fetcher 类）
  event   - 事件日历        （2 个模块：eastmoney/performance_forecast，6 个 fetcher 类）
  chip    - 融资融券/股东   （1 个模块：eastmoney，3 个 fetcher 类）
  _common - 内部辅助        （1 个模块：pytdx_pool，非 fetcher）
"""

import logging
import threading

from common import BaseFetcher, DataFetcherManager

logger = logging.getLogger(__name__)

# 工厂函数缓存：避免每次调用创建新的 fetcher 实例（含 CircuitBreaker）
_fetcher_cache: dict[str, list] = {}
_cache_lock = threading.Lock()


def _try_import(module_name, class_name):
    """尝试导入模块，失败返回 None。

    P1-03: 仅捕获 ImportError/AttributeError（依赖未安装或类不存在），
    其他异常（SyntaxError/TypeError 等模块级 bug）打 warning 并 re-raise，
    避免掩盖真实的 fetcher 模块缺陷。
    """
    try:
        import importlib

        mod = importlib.import_module(f".{module_name}", package=__name__)
        return getattr(mod, class_name, None)
    except (ImportError, AttributeError) as e:
        logger.debug("可选依赖 %s.%s 加载失败: %s", module_name, class_name, e)
        return None


# ═══════════════════════════════════════════════════════════════
# 数据域: quote（行情）
# ═══════════════════════════════════════════════════════════════


def get_quote_fetchers() -> list:
    """获取所有可用的行情数据源（缓存单例）。"""
    if "quote" in _fetcher_cache:
        return _fetcher_cache["quote"]
    with _cache_lock:
        if "quote" in _fetcher_cache:
            return _fetcher_cache["quote"]
        fetchers = []

        # 直接 HTTP 数据源（无依赖）
        from .quote.tencent_quote import TencentQuoteFetcher
        from .quote.eastmoney_quote import EastmoneyQuoteFetcher
        from .quote.sina_quote import SinaQuoteFetcher
        from .quote.xueqiu_quote import XueqiuQuoteFetcher
        from .quote.ths_quote import ThsQuoteFetcher

        fetchers.extend(
            [
                TencentQuoteFetcher(),
                EastmoneyQuoteFetcher(),
                SinaQuoteFetcher(),
                XueqiuQuoteFetcher(),
                ThsQuoteFetcher(),
            ]
        )

        # 可选依赖数据源
        for mod, cls in [
            ("quote.efinance_quote", "EfinanceQuoteFetcher"),
            ("quote.akshare_quote", "AkshareQuoteFetcher"),
            ("quote.tushare_quote", "TushareQuoteFetcher"),
            ("quote.pytdx_quote", "PytdxQuoteFetcher"),
            ("quote.yfinance_quote", "YfinanceQuoteFetcher"),
        ]:
            c = _try_import(mod, cls)
            if c:
                fetchers.append(c())

        _fetcher_cache["quote"] = fetchers
        return fetchers


# ═══════════════════════════════════════════════════════════════
# 数据域: kline（K 线）
# ═══════════════════════════════════════════════════════════════


def get_kline_fetchers() -> list:
    """获取所有可用的 K 线数据源（缓存单例）。"""
    if "kline" in _fetcher_cache:
        return _fetcher_cache["kline"]
    with _cache_lock:
        if "kline" in _fetcher_cache:
            return _fetcher_cache["kline"]
        fetchers = []

        from .kline.sina_kline import SinaKlineFetcher
        from .kline.eastmoney_kline import EastmoneyKlineFetcher
        from .kline.tencent_kline import TencentKlineFetcher

        fetchers.extend(
            [SinaKlineFetcher(), EastmoneyKlineFetcher(), TencentKlineFetcher()]
        )

        for mod, cls in [
            ("kline.efinance_kline", "EfinanceKlineFetcher"),
            ("kline.akshare_kline", "AkshareKlineFetcher"),
            ("kline.tushare_kline", "TushareKlineFetcher"),
            ("kline.baostock_kline", "BaostockKlineFetcher"),
            ("kline.yfinance_kline", "YfinanceKlineFetcher"),
            ("kline.pytdx_kline", "PytdxKlineFetcher"),
        ]:
            c = _try_import(mod, cls)
            if c:
                fetchers.append(c())

        _fetcher_cache["kline"] = fetchers
        return fetchers


# ═══════════════════════════════════════════════════════════════
# 数据域: finance（财务）
# ═══════════════════════════════════════════════════════════════


def get_finance_fetchers() -> list:
    """获取所有可用的财务数据源（缓存单例）。"""
    if "finance" in _fetcher_cache:
        return _fetcher_cache["finance"]
    with _cache_lock:
        if "finance" in _fetcher_cache:
            return _fetcher_cache["finance"]
        fetchers = []

        from .finance.eastmoney_finance import EastmoneyFinanceFetcher

        fetchers.append(EastmoneyFinanceFetcher())

        for mod, cls in [
            ("finance.akshare_finance", "AkshareFinanceFetcher"),
        ]:
            c = _try_import(mod, cls)
            if c:
                fetchers.append(c())

        _fetcher_cache["finance"] = fetchers
        return fetchers


# ═══════════════════════════════════════════════════════════════
# 数据域: flow（资金流向）
# ═══════════════════════════════════════════════════════════════


def get_flow_fetchers() -> list:
    """获取所有可用的资金流向数据源（缓存单例）。"""
    if "flow" in _fetcher_cache:
        return _fetcher_cache["flow"]
    with _cache_lock:
        if "flow" in _fetcher_cache:
            return _fetcher_cache["flow"]
        fetchers = []

        from .flow.eastmoney_flow import NorthboundFlowFetcher, StockFlowFetcher
        from .flow.sina_flow import SinaNorthboundFlowFetcher

        fetchers.extend(
            [NorthboundFlowFetcher(), StockFlowFetcher(), SinaNorthboundFlowFetcher()]
        )

        _fetcher_cache["flow"] = fetchers
        return fetchers


# ═══════════════════════════════════════════════════════════════
# 数据域: lhb（龙虎榜）
# ═══════════════════════════════════════════════════════════════


def get_lhb_fetchers() -> list:
    """获取所有可用的龙虎榜数据源（缓存单例）。"""
    if "lhb" in _fetcher_cache:
        return _fetcher_cache["lhb"]
    with _cache_lock:
        if "lhb" in _fetcher_cache:
            return _fetcher_cache["lhb"]
        fetchers = []

        from .lhb.eastmoney_lhb import LhbDetailFetcher, LhbSeatFetcher

        fetchers.extend([LhbDetailFetcher(), LhbSeatFetcher()])

        _fetcher_cache["lhb"] = fetchers
        return fetchers


# ═══════════════════════════════════════════════════════════════
# 数据域: event（事件日历）
# ═══════════════════════════════════════════════════════════════


def get_event_fetchers() -> list:
    """获取所有可用的事件日历数据源（缓存单例）。

    calendar 类（3 个）：EarningsCalendarFetcher / LockupCalendarFetcher / DividendCalendarFetcher
    个股类（2 个）：ShareholderChangeFetcher / ViolationFetcher
    """
    if "event" in _fetcher_cache:
        return _fetcher_cache["event"]
    with _cache_lock:
        if "event" in _fetcher_cache:
            return _fetcher_cache["event"]
        fetchers = []

        from .event.eastmoney_event import (
            EarningsCalendarFetcher,
            LockupCalendarFetcher,
            DividendCalendarFetcher,
            ShareholderChangeFetcher,
            ViolationFetcher,
        )
        from .event.performance_forecast import PerformanceForecastFetcher

        fetchers.extend(
            [
                EarningsCalendarFetcher(),
                LockupCalendarFetcher(),
                DividendCalendarFetcher(),
                ShareholderChangeFetcher(),
                ViolationFetcher(),
                PerformanceForecastFetcher(),
            ]
        )

        _fetcher_cache["event"] = fetchers
        return fetchers


# ═══════════════════════════════════════════════════════════════
# 数据域: chip（融资融券/股东/十大流通股东）
# ═══════════════════════════════════════════════════════════════


def get_chip_fetchers() -> list:
    """获取所有可用的筹码相关数据源（缓存单例）。"""
    if "chip" in _fetcher_cache:
        return _fetcher_cache["chip"]
    with _cache_lock:
        if "chip" in _fetcher_cache:
            return _fetcher_cache["chip"]
        fetchers = []

        from .chip.eastmoney_chip import MarginFetcher, HolderFetcher, TopHolderFetcher

        fetchers.extend([MarginFetcher(), HolderFetcher(), TopHolderFetcher()])

        _fetcher_cache["chip"] = fetchers
        return fetchers


# ═══════════════════════════════════════════════════════════════
# 数据域 → fetcher 工厂注册表（v1.3.2 新增）
# ═══════════════════════════════════════════════════════════════

_DOMAIN_FACTORIES = {
    "quote": get_quote_fetchers,
    "kline": get_kline_fetchers,
    "finance": get_finance_fetchers,
    "flow": get_flow_fetchers,
    "lhb": get_lhb_fetchers,
    "event": get_event_fetchers,
    "chip": get_chip_fetchers,
}


def list_data_domains() -> list:
    """列出所有支持的数据域。"""
    return list(_DOMAIN_FACTORIES.keys())


def get_fetchers_by_domain(domain: str) -> list:
    """按数据域获取 fetcher 列表。未知域抛 ValueError。

    Args:
        domain: 数据域名（quote/kline/finance/flow/lhb/event/chip）

    Returns:
        该域下所有可用的 fetcher 实例列表
    """
    if domain not in _DOMAIN_FACTORIES:
        raise ValueError(f"未知数据域: {domain}，可用: {list_data_domains()}")
    return _DOMAIN_FACTORIES[domain]()


# 全局管理器（线程安全延迟初始化）
_manager_lock = threading.Lock()
_managers: dict[str, DataFetcherManager] = {}


def _load_source_config(section: str) -> dict:
    """从 data_source.yaml 加载指定数据域的配置节。

    Args:
        section: YAML 配置节名（如 "quote_sources"）

    Returns:
        配置字典，加载失败时返回空 dict
    """
    try:
        from config.loader import ConfigLoader

        return ConfigLoader.load("data_source.yaml").get(section, {})
    except Exception as e:
        import logging

        logging.getLogger(__name__).debug("加载数据源配置 %s 失败: %s", section, e)
        return {}


def _get_or_create(
    domain: str, factory, source_section: str | None = None
) -> DataFetcherManager:
    """线程安全的管理器获取。"""
    mgr = _managers.get(domain)
    if mgr is not None:
        return mgr
    with _manager_lock:
        if domain not in _managers:
            cfg = _load_source_config(source_section) if source_section else {}
            _managers[domain] = DataFetcherManager(factory(), source_config=cfg)
        return _managers[domain]


def get_quote_manager() -> DataFetcherManager:
    return _get_or_create("quote", get_quote_fetchers, "quote_sources")


def get_kline_manager() -> DataFetcherManager:
    return _get_or_create("kline", get_kline_fetchers, "kline_sources")


def get_finance_manager() -> DataFetcherManager:
    return _get_or_create("finance", get_finance_fetchers, "finance_sources")


def get_flow_manager() -> DataFetcherManager:
    return _get_or_create("flow", get_flow_fetchers, "flow_sources")


def get_lhb_manager() -> DataFetcherManager:
    return _get_or_create("lhb", get_lhb_fetchers, "lhb_sources")


def get_event_manager() -> DataFetcherManager:
    return _get_or_create("event", get_event_fetchers, "event_sources")


def get_chip_manager() -> DataFetcherManager:
    return _get_or_create("chip", get_chip_fetchers, "chip_sources")
