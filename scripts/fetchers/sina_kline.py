"""新浪 K 线数据源。"""

import json
from pathlib import Path

from common import BaseFetcher, http_get

SINA_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale={scale}&ma=no&datalen={datalen}"


class SinaKlineFetcher(BaseFetcher):
    """新浪 K 线数据源 (优先级 10)。"""

    def __init__(self):
        super().__init__("sina_kline", priority=10)

    def fetch(self, code: str, **kwargs) -> list | None:
        scale = kwargs.get("scale", 240)
        datalen = kwargs.get("datalen", 30)
        timeout = kwargs.get("timeout", 15)
        raw = http_get(
            SINA_URL.format(symbol=code, scale=scale, datalen=datalen), timeout=timeout
        )
        try:
            records = json.loads(raw)
            if records:
                for r in records:
                    r["source"] = "sina"
                return records
            return None
        except json.JSONDecodeError:
            return None
