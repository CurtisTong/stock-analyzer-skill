"""akshare 行情数据源（需要 akshare 包）。"""

import logging

from fetchers.quote._base_bulk import BaseBulkQuoteFetcher

logger = logging.getLogger(__name__)

try:
    import akshare as ak

    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False


class AkshareQuoteFetcher(BaseBulkQuoteFetcher):
    """akshare 行情数据源 (优先级 1) - 需要安装 akshare 包。"""

    def __init__(self):
        super().__init__("akshare_quote", priority=1)

    def _sdk_available(self) -> bool:
        return HAS_AKSHARE

    def _fetch_bulk_df(self):
        # 锁外网络 IO：拉取全市场行情（数千行，耗时数秒）
        return ak.stock_zh_a_spot_em()

    def _code_column(self) -> str:
        return "代码"

    def _name_column(self) -> str:
        return "名称"

    def _source(self) -> str:
        return "akshare"

    def _index_column(self) -> str | None:
        # 以"代码"为索引，避免每次 fetch O(n) 线性扫描
        return "代码"
