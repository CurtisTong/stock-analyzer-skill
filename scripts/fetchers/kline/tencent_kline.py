"""腾讯 K 线数据源。"""

import json
import logging

from common import BaseFetcher, http_get

logger = logging.getLogger(__name__)

# P2-2: 文档建议 ifzq 用 https（http 可能被运营商劫持/重定向失败）。
# 实测 https 可用且返回与 http 一致，故采用 https。
TENCENT_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={stockCode},{period},,,{count},qfq"
SCALE_MAP = {5: "m5", 15: "m15", 30: "m30", 60: "m60", 240: "day"}
# 腾讯 ifzq kline 固定最多返回 640 个交易日（实测上限，文档记载）。
# 请求 count 超过此值会被静默截断，故在此钳位并在截断时记录日志。
TENCENT_MAX_BARS = 640


class TencentKlineFetcher(BaseFetcher):
    """腾讯 K 线数据源 (优先级 5)。"""

    def __init__(self):
        super().__init__("tencent_kline", priority=5)

    def fetch(self, code: str, **kwargs) -> list | None:
        scale = kwargs.get("scale", 240)
        datalen = kwargs.get("datalen", 30)
        period = SCALE_MAP.get(scale, "day")
        # P1-2: 钳位 datalen，避免超过 ifzq 640 日上限被静默截断。
        # 取 self.max_datalen（yaml 配置）与 TENCENT_MAX_BARS 的较小值作为上限。
        upper = TENCENT_MAX_BARS
        if self.max_datalen and self.max_datalen < upper:
            upper = self.max_datalen
        if datalen > upper:
            logger.debug(
                "tencent_kline datalen %d 超过上限 %d，已钳位（数据将被截断）",
                datalen,
                upper,
            )
            datalen = upper
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
