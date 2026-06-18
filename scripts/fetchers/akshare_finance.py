"""akshare 财务数据源（需要 akshare 包）。"""
import logging
from pathlib import Path

from common import BaseFetcher

logger = logging.getLogger(__name__)

try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False


class AkshareFinanceFetcher(BaseFetcher):
    """akshare 财务数据源 (优先级 3) - 需要安装 akshare 包。"""

    def __init__(self):
        super().__init__("akshare_finance", priority=3)

    def fetch(self, code: str, **kwargs) -> list | None:
        if not HAS_AKSHARE:
            return None
        try:
            plain = code.lstrip("shszSHSZbjBJ")
            df = ak.stock_financial_abstract(symbol=plain)
            if df is None or df.empty:
                return None
            # 返回最近 4 季
            result = []
            for _, row in df.head(4).iterrows():
                result.append(row.to_dict())
            return result if result else None
        except Exception as e:
            logger.debug("akshare_finance 获取失败 %s: %s", code, e)
            return None
