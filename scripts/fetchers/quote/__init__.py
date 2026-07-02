"""quote 数据域：实时行情 fetcher 集合。

仅 re-export 无第三方依赖的 fetcher（tencent/eastmoney/sina/xueqiu/ths）；
可选依赖 fetcher（efinance/akshare/tushare/pytdx/yfinance）通过显式路径
import（如 from fetchers.quote.pytdx_quote import PytdxQuoteFetcher），
避免在第三方包未安装时预加载导致模块级 HAS_PYTDX 等标志被缓存为 False。
"""

from .tencent_quote import TencentQuoteFetcher
from .eastmoney_quote import EastmoneyQuoteFetcher
from .sina_quote import SinaQuoteFetcher
from .xueqiu_quote import XueqiuQuoteFetcher
from .ths_quote import ThsQuoteFetcher

__all__ = [
    "TencentQuoteFetcher",
    "EastmoneyQuoteFetcher",
    "SinaQuoteFetcher",
    "XueqiuQuoteFetcher",
    "ThsQuoteFetcher",
    # 可选依赖（不在此 re-export，需显式路径 import）：
    # "EfinanceQuoteFetcher",
    # "AkshareQuoteFetcher",
    # "TushareQuoteFetcher",
    # "PytdxQuoteFetcher",
    # "YfinanceQuoteFetcher",
]
