"""kline 数据域：K 线 fetcher 集合。

仅 re-export 无第三方依赖的 fetcher（sina/eastmoney/tencent）；
可选依赖 fetcher（efinance/akshare/tushare/baostock/pytdx/yfinance）
通过显式路径 import，避免预加载导致模块级标志被缓存。
"""

from .sina_kline import SinaKlineFetcher
from .eastmoney_kline import EastmoneyKlineFetcher
from .tencent_kline import TencentKlineFetcher

__all__ = [
    "SinaKlineFetcher",
    "EastmoneyKlineFetcher",
    "TencentKlineFetcher",
    # 可选依赖（不在此 re-export，需显式路径 import）：
    # "EfinanceKlineFetcher",
    # "AkshareKlineFetcher",
    # "TushareKlineFetcher",
    # "BaostockKlineFetcher",
    # "PytdxKlineFetcher",
    # "YfinanceKlineFetcher",
]
