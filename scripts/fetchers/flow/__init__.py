"""flow 数据域：资金流向 fetcher 集合。"""

from .eastmoney_flow import NorthboundFlowFetcher, StockFlowFetcher

__all__ = [
    "NorthboundFlowFetcher",
    "StockFlowFetcher",
]
