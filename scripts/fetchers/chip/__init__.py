"""chip 数据域：融资融券/股东 fetcher 集合。"""

from .eastmoney_chip import MarginFetcher, HolderFetcher, TopHolderFetcher

__all__ = [
    "MarginFetcher",
    "HolderFetcher",
    "TopHolderFetcher",
]
