"""腾讯 K 线数据源。"""

import json

from common import BaseFetcher, http_get

TENCENT_URL = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={stockCode},{period},,,{count},qfq"
SCALE_MAP = {5: "m5", 15: "m15", 30: "m30", 60: "m60", 240: "day"}


class TencentKlineFetcher(BaseFetcher):
    """腾讯 K 线数据源 (优先级 5)。"""

    def __init__(self):
        super().__init__("tencent_kline", priority=5)

    def fetch(self, code: str, **kwargs) -> list | None:
        scale = kwargs.get("scale", 240)
        datalen = kwargs.get("datalen", 30)
        period = SCALE_MAP.get(scale, "day")
        url = TENCENT_URL.format(stockCode=code, period=period, count=datalen)
        raw = http_get(url, timeout=self.timeout, max_retries=self.retry)
        try:
            resp = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if resp.get("code") != 0 or "data" not in resp:
            return None
        stock_data = resp["data"].get(code, {})
        key_candidates = [f"qfq{period}", period]
        records = []
        for key in key_candidates:
            if key in stock_data:
                records = stock_data[key]
                break
        if not records:
            return None
        result = []
        for row in records:
            if len(row) >= 6:
                result.append(
                    {
                        "day": row[0],
                        "open": row[1],
                        "high": row[3],
                        "low": row[4],
                        "close": row[2],
                        "volume": row[5],
                        "source": "tencent",
                    }
                )
        return result if result else None
