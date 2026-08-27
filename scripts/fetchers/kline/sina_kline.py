"""新浪 K 线数据源。

.. note::
    新浪 API 不支持复权参数，返回不复权数据。除权日 OHLC 会跳变，
    与前复权源（eastmoney/tencent）混用会导致技术指标错误。
    因此优先级从 10 降为 3，让支持前复权的源优先命中。
"""

import json

from common import BaseFetcher, http_get
from common.exceptions import (
    HTTPStatusError,
    NetworkError,
    ParseError,
    RateLimitError,
)

# 新浪 K 线接口（与 quote 的 hq.sinajs.cn 不同，走 quotes_service）。
# 查询参数：
#   symbol   股票代码（带交易所前缀，如 sh600989）
#   scale    K 线周期（分钟）：240=日线, 60=60分钟, 30=30分钟, 5=5分钟...
#   ma=no    不返回均线数据（本项目自行计算 MA）
#   datalen  返回 K 线根数（上限约 1023，超出返回空）
SINA_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale={scale}&ma=no&datalen={datalen}"


class SinaKlineFetcher(BaseFetcher):
    """新浪 K 线数据源 (优先级 3)。

    .. warning:: 不支持复权，返回不复权数据。优先级低于 eastmoney(8)/tencent(5)。
    """

    def __init__(self):
        super().__init__("sina_kline", priority=3)

    def fetch(self, code: str, **kwargs) -> list | None:
        scale = kwargs.get("scale", 240)
        datalen = kwargs.get("datalen", 30)
        # 新浪 API datalen 上限约 1023，超出返回空
        datalen = min(int(datalen), 1023)
        timeout = kwargs.get("timeout", self.timeout)
        raw = http_get(
            SINA_URL.format(symbol=code, scale=scale, datalen=datalen),
            timeout=timeout,
            max_retries=self.retry,
        )
        try:
            records = json.loads(raw)
            if records:
                for r in records:
                    r["source"] = "sina"
                return records
            return None
        except (NetworkError, RateLimitError, HTTPStatusError, ParseError):
            raise  # 网络/限速/解析异常向上抛，触发熔断和退避
        except json.JSONDecodeError:
            return None
