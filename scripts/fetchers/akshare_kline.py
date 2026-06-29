"""akshare K 线数据源（需要 akshare 包）。"""

import logging
from pathlib import Path

from common import BaseFetcher

logger = logging.getLogger(__name__)

try:
    import akshare as ak

    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False


class AkshareKlineFetcher(BaseFetcher):
    """akshare K 线数据源 (优先级 1) - 需要安装 akshare 包。"""

    def __init__(self):
        super().__init__("akshare_kline", priority=1)

    def fetch(self, code: str, **kwargs) -> list | None:
        if not HAS_AKSHARE:
            return None
        try:
            scale = kwargs.get("scale", 240)
            datalen = kwargs.get("datalen", 30)
            plain = code.lstrip("shszSHSZbjBJ")

            if scale == 240:
                # 日 K
                df = ak.stock_zh_a_hist(symbol=plain, period="daily", adjust="qfq")
            elif scale == 60:
                df = ak.stock_zh_a_hist(symbol=plain, period="60", adjust="qfq")
            elif scale == 30:
                df = ak.stock_zh_a_hist(symbol=plain, period="30", adjust="qfq")
            elif scale == 15:
                df = ak.stock_zh_a_hist(symbol=plain, period="15", adjust="qfq")
            elif scale == 5:
                df = ak.stock_zh_a_hist(symbol=plain, period="5", adjust="qfq")
            else:
                df = ak.stock_zh_a_hist(symbol=plain, period="daily", adjust="qfq")

            if df is None or df.empty:
                return None

            df = df.tail(datalen)
            result = []
            for _, row in df.iterrows():
                result.append(
                    {
                        "day": str(row.get("日期", ""))[:10],
                        "open": str(row.get("开盘", 0)),
                        "close": str(row.get("收盘", 0)),
                        "high": str(row.get("最高", 0)),
                        "low": str(row.get("最低", 0)),
                        "volume": str(row.get("成交量", 0)),
                    }
                )
            return result if result else None
        except Exception as e:
            logger.debug("akshare_kline 获取失败 %s: %s", code, e)
            return None
