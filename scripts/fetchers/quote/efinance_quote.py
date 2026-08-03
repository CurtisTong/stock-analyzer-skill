"""efinance 行情数据源（需要 efinance 包）。"""

import logging

from fetchers.quote._base_bulk import BaseBulkQuoteFetcher

logger = logging.getLogger(__name__)

try:
    import efinance as ef

    HAS_EFINANCE = True
except ImportError:
    HAS_EFINANCE = False


class EfinanceQuoteFetcher(BaseBulkQuoteFetcher):
    """efinance 行情数据源 (优先级 0) - 需要安装 efinance 包。"""

    def __init__(self):
        super().__init__("efinance_quote", priority=0)

    def _sdk_available(self) -> bool:
        return HAS_EFINANCE

    def _fetch_bulk_df(self):
        # 锁外网络 IO：拉取全市场行情（数千行，耗时数秒）
        return ef.stock.get_realtime_quotes()

    def _code_column(self) -> str:
        return "股票代码"

    def _name_column(self) -> str:
        return "股票名称"

    def _source(self) -> str:
        return "efinance"

    def _index_column(self) -> str | None:
        # efinance 不索引化，行查找走线性扫描
        return None
