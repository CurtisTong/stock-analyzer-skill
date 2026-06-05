"""
数据源集合：自动发现并加载可用的数据源。
依赖包未安装时自动跳过对应数据源。
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
        return getattr(mod, class_name)
    except (ImportError, AttributeError):
        return None


def get_quote_fetchers() -> list:
    """获取所有可用的行情数据源。"""
    fetchers = []

    # 直接 HTTP 数据源（无依赖）
    from .tencent_quote import TencentQuoteFetcher
    from .eastmoney_quote import EastmoneyQuoteFetcher
    from .sina_quote import SinaQuoteFetcher
    fetchers.extend([TencentQuoteFetcher(), EastmoneyQuoteFetcher(), SinaQuoteFetcher()])

    # 可选依赖数据源
    cls = _try_import("efinance_quote", "EfinanceQuoteFetcher")
    if cls:
        fetchers.append(cls())

    cls = _try_import("akshare_quote", "AkshareQuoteFetcher")
    if cls:
        fetchers.append(cls())

    cls = _try_import("tushare_quote", "TushareQuoteFetcher")
    if cls:
        fetchers.append(cls())

    cls = _try_import("pytdx_quote", "PytdxQuoteFetcher")
    if cls:
        fetchers.append(cls())

    return fetchers


def get_kline_fetchers() -> list:
    """获取所有可用的 K 线数据源。"""
    fetchers = []

    # 直接 HTTP 数据源（无依赖）
    from .sina_kline import SinaKlineFetcher
    from .eastmoney_kline import EastmoneyKlineFetcher
    from .tencent_kline import TencentKlineFetcher
    fetchers.extend([SinaKlineFetcher(), EastmoneyKlineFetcher(), TencentKlineFetcher()])

    # 可选依赖数据源
    cls = _try_import("efinance_kline", "EfinanceKlineFetcher")
    if cls:
        fetchers.append(cls())

    cls = _try_import("akshare_kline", "AkshareKlineFetcher")
    if cls:
        fetchers.append(cls())

    cls = _try_import("tushare_kline", "TushareKlineFetcher")
    if cls:
        fetchers.append(cls())

    cls = _try_import("baostock_kline", "BaostockKlineFetcher")
    if cls:
        fetchers.append(cls())

    cls = _try_import("yfinance_kline", "YfinanceKlineFetcher")
    if cls:
        fetchers.append(cls())

    return fetchers


def get_finance_fetchers() -> list:
    """获取所有可用的财务数据源。"""
    fetchers = []

    from .eastmoney_finance import EastmoneyFinanceFetcher
    fetchers.append(EastmoneyFinanceFetcher())

    cls = _try_import("efinance_finance", "EfinanceFinanceFetcher")
    if cls:
        fetchers.append(cls())

    cls = _try_import("akshare_finance", "AkshareFinanceFetcher")
    if cls:
        fetchers.append(cls())

    return fetchers


# 全局管理器（延迟初始化）
_quote_manager = None
_kline_manager = None
_finance_manager = None


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
