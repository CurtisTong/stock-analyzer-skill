"""finance 数据域：财务 fetcher 集合。

仅 re-export 无第三方依赖的 fetcher（eastmoney）；
可选依赖 fetcher（akshare）通过显式路径 import。
"""

from .eastmoney_finance import EastmoneyFinanceFetcher

__all__ = [
    "EastmoneyFinanceFetcher",
    # 可选依赖（不在此 re-export，需显式路径 import）：
    # "AkshareFinanceFetcher",
]
