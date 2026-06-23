"""
数据源集合：自动发现并加载可用的数据源。
依赖包未安装时自动跳过对应数据源。

v1.3.2 起按数据域分组（7 个数据域 × 21 个 fetcher），便于扩展时定位代码。
文件保持平铺以避免破坏 import 路径；如需子目录化请参考 docs/improvement-roadmap.md。

数据域分块：
  quote   - 实时行情        （9 个：tencent/eastmoney/sina/xueqiu/ths/efinance/akshare/tushare/pytdx）
  kline   - K 线            （9 个：sina/eastmoney/tencent/efinance/akshare/tushare/baostock/pytdx/yfinance）
  finance - 财务            （3 个：eastmoney/efinance/akshare）
  flow    - 资金流向        （1 个：eastmoney）
  lhb     - 龙虎榜          （1 个：eastmoney）
  event   - 事件日历        （1 个：eastmoney）
  chip    - 融资融券/股东   （1 个：eastmoney）
"""

import logging
import threading

from common import BaseFetcher, DataFetcherManager

logger = logging.getLogger(__name__)


def _try_import(module_name, class_name):
    """尝试导入模块，失败返回 None。"""
    try:
        import importlib

        mod = importlib.import_module(f".{module_name}", package=__name__)
        return getattr(mod, class_name, None)
    except Exception as e:
        logger.debug("可选依赖 %s.%s 加载失败: %s", module_name, class_name, e)
        return None


# ═══════════════════════════════════════════════════════════════
# 数据域: quote（行情）
# ═══════════════════════════════════════════════════════════════


def get_quote_fetchers() -> list:
    """获取所有可用的行情数据源。"""
    fetchers = []

    # 直接 HTTP 数据源（无依赖）
    from .tencent_quote import TencentQuoteFetcher
    from .eastmoney_quote import EastmoneyQuoteFetcher
    from .sina_quote import SinaQuoteFetcher
    from .xueqiu_quote import XueqiuQuoteFetcher
    from .ths_quote import ThsQuoteFetcher

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
        ("efinance_quote", "EfinanceQuoteFetcher"),
        ("akshare_quote", "AkshareQuoteFetcher"),
        ("tushare_quote", "TushareQuoteFetcher"),
        ("pytdx_quote", "PytdxQuoteFetcher"),
        ("yfinance_quote", "YfinanceQuoteFetcher"),
    ]:
        c = _try_import(mod, cls)
        if c:
            fetchers.append(c())

    return fetchers


# ═══════════════════════════════════════════════════════════════
# 数据域: kline（K 线）
# ═══════════════════════════════════════════════════════════════


def get_kline_fetchers() -> list:
    """获取所有可用的 K 线数据源。"""
    fetchers = []

    from .sina_kline import SinaKlineFetcher
    from .eastmoney_kline import EastmoneyKlineFetcher
    from .tencent_kline import TencentKlineFetcher

    fetchers.extend(
        [SinaKlineFetcher(), EastmoneyKlineFetcher(), TencentKlineFetcher()]
    )

    for mod, cls in [
        ("efinance_kline", "EfinanceKlineFetcher"),
        ("akshare_kline", "AkshareKlineFetcher"),
        ("tushare_kline", "TushareKlineFetcher"),
        ("baostock_kline", "BaostockKlineFetcher"),
        ("yfinance_kline", "YfinanceKlineFetcher"),
        ("pytdx_kline", "PytdxKlineFetcher"),
    ]:
        c = _try_import(mod, cls)
        if c:
            fetchers.append(c())

    return fetchers


# ═══════════════════════════════════════════════════════════════
# 数据域: finance（财务）
# ═══════════════════════════════════════════════════════════════


def get_finance_fetchers() -> list:
    """获取所有可用的财务数据源。"""
    fetchers = []

    from .eastmoney_finance import EastmoneyFinanceFetcher

    fetchers.append(EastmoneyFinanceFetcher())

    for mod, cls in [
        ("efinance_finance", "EfinanceFinanceFetcher"),
        ("akshare_finance", "AkshareFinanceFetcher"),
    ]:
        c = _try_import(mod, cls)
        if c:
            fetchers.append(c())

    return fetchers


# ═══════════════════════════════════════════════════════════════
# 数据域: flow（资金流向）
# ═══════════════════════════════════════════════════════════════


def get_flow_fetchers() -> list:
    """获取所有可用的资金流向数据源。"""
    fetchers = []

    from .eastmoney_flow import NorthboundFlowFetcher, StockFlowFetcher

    fetchers.extend([NorthboundFlowFetcher(), StockFlowFetcher()])

    return fetchers


# ═══════════════════════════════════════════════════════════════
# 数据域: lhb（龙虎榜）
# ═══════════════════════════════════════════════════════════════


def get_lhb_fetchers() -> list:
    """获取所有可用的龙虎榜数据源。"""
    fetchers = []

    from .eastmoney_lhb import LhbDetailFetcher, LhbSeatFetcher

    fetchers.extend([LhbDetailFetcher(), LhbSeatFetcher()])

    return fetchers


# ═══════════════════════════════════════════════════════════════
# 数据域: event（事件日历）
# ═══════════════════════════════════════════════════════════════


def get_event_fetchers() -> list:
    """获取所有可用的事件日历数据源。"""
    fetchers = []

    from .eastmoney_event import (
        EarningsCalendarFetcher,
        LockupCalendarFetcher,
        DividendCalendarFetcher,
    )

    fetchers.extend(
        [EarningsCalendarFetcher(), LockupCalendarFetcher(), DividendCalendarFetcher()]
    )

    return fetchers


# ═══════════════════════════════════════════════════════════════
# 数据域: chip（融资融券/股东/十大流通股东）
# ═══════════════════════════════════════════════════════════════


def get_chip_fetchers() -> list:
    """获取所有可用的筹码相关数据源。"""
    fetchers = []

    from .eastmoney_chip import MarginFetcher, HolderFetcher, TopHolderFetcher

    fetchers.extend([MarginFetcher(), HolderFetcher(), TopHolderFetcher()])

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
    return _get_or_create("flow", get_flow_fetchers)


def get_lhb_manager() -> DataFetcherManager:
    return _get_or_create("lhb", get_lhb_fetchers)


def get_event_manager() -> DataFetcherManager:
    return _get_or_create("event", get_event_fetchers)


def get_chip_manager() -> DataFetcherManager:
    return _get_or_create("chip", get_chip_fetchers)
