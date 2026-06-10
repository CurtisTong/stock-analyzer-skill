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
import sys
from pathlib import Path

# 添加 scripts 目录到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import BaseFetcher, DataFetcherManager


def _try_import(module_name, class_name):
    """尝试导入模块，失败返回 None。"""
    try:
        import importlib
        mod = importlib.import_module(f".{module_name}", package=__name__)
        return getattr(mod, class_name, None)
    except Exception:
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
    fetchers.extend([
        TencentQuoteFetcher(),
        EastmoneyQuoteFetcher(),
        SinaQuoteFetcher(),
        XueqiuQuoteFetcher(),
        ThsQuoteFetcher(),
    ])

    # 可选依赖数据源
    for mod, cls in [
        ("efinance_quote", "EfinanceQuoteFetcher"),
        ("akshare_quote", "AkshareQuoteFetcher"),
        ("tushare_quote", "TushareQuoteFetcher"),
        ("pytdx_quote", "PytdxQuoteFetcher"),
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
    fetchers.extend([SinaKlineFetcher(), EastmoneyKlineFetcher(), TencentKlineFetcher()])

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

    from .eastmoney_event import EarningsCalendarFetcher, LockupCalendarFetcher, DividendCalendarFetcher
    fetchers.extend([EarningsCalendarFetcher(), LockupCalendarFetcher(), DividendCalendarFetcher()])

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
        raise ValueError(
            f"未知数据域: {domain}，可用: {list_data_domains()}"
        )
    return _DOMAIN_FACTORIES[domain]()


# 全局管理器（延迟初始化）
_quote_manager = None
_kline_manager = None
_finance_manager = None
_flow_manager = None
_lhb_manager = None
_event_manager = None
_chip_manager = None


def get_quote_manager() -> DataFetcherManager:
    global _quote_manager
    if _quote_manager is None:
        _quote_manager = DataFetcherManager(get_quote_fetchers())
    return _quote_manager


def get_kline_manager() -> DataFetcherManager:
    global _kline_manager
    if _kline_manager is None:
        _kline_manager = DataFetcherManager(get_kline_fetchers())
    return _kline_manager


def get_finance_manager() -> DataFetcherManager:
    global _finance_manager
    if _finance_manager is None:
        _finance_manager = DataFetcherManager(get_finance_fetchers())
    return _finance_manager


def get_flow_manager() -> DataFetcherManager:
    global _flow_manager
    if _flow_manager is None:
        _flow_manager = DataFetcherManager(get_flow_fetchers())
    return _flow_manager


def get_lhb_manager() -> DataFetcherManager:
    global _lhb_manager
    if _lhb_manager is None:
        _lhb_manager = DataFetcherManager(get_lhb_fetchers())
    return _lhb_manager


def get_event_manager() -> DataFetcherManager:
    global _event_manager
    if _event_manager is None:
        _event_manager = DataFetcherManager(get_event_fetchers())
    return _event_manager


def get_chip_manager() -> DataFetcherManager:
    global _chip_manager
    if _chip_manager is None:
        _chip_manager = DataFetcherManager(get_chip_fetchers())
    return _chip_manager
