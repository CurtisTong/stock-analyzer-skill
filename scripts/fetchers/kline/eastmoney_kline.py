"""东方财富 K 线数据源。"""

import json
import logging
import os

from common import BaseFetcher, http_get, to_secid

logger = logging.getLogger(__name__)

# ut token 从环境变量读取，未配置时为空（API 调用需自行保证 token 有效）
_UT = os.environ.get("EASTMONEY_UT_TOKEN", "")

# v1.16.0 D-A.2: token 通过 urlencode 加入查询串（防止 token 出现在 referer/proxy/调试日志）
# URL 模板不含 ut；fetch() 时把 ut 当成 query param 用 urlencode 加入。
EASTMONEY_KLINE_URL = (
    "https://push2his.eastmoney.com/api/qt/stock/kline/get?cb=&secid={secid}"
    "&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
    "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
    "&klt={klt}&fqt=1&end=20500101&lmt={lmt}"
)
KLT_MAP = {5: 5, 15: 15, 30: 30, 60: 60, 240: 101}


class EastmoneyKlineFetcher(BaseFetcher):
    """东方财富 K 线数据源 (优先级 8)。"""

    def __init__(self):
        super().__init__("eastmoney_kline", priority=8)

    def fetch(self, code: str, **kwargs) -> list | None:
        from urllib.parse import urlencode

        scale = kwargs.get("scale", 240)
        datalen = kwargs.get("datalen", 30)
        secid = to_secid(code)
        klt = KLT_MAP.get(scale, 101)
        if not _UT:
            logger.debug("东方财富 K 线: EASTMONEY_UT_TOKEN 未配置，使用空 token 尝试")
        # v1.16.0 D-A.2: 用 urlencode 包装 token，避免拼接 URL 时泄漏到 referer/proxy 日志
        base_url = EASTMONEY_KLINE_URL.format(secid=secid, klt=klt, lmt=datalen)
        if _UT:
            ut_query = urlencode({"ut": _UT})
            url = f"{base_url}&{ut_query}"
        else:
            url = base_url
        raw = http_get(url, timeout=self.timeout, max_retries=self.retry)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("东方财富 K 线 JSON 解析失败: %s", code)
            return None
        if not data or data.get("rc") != 0 or "data" not in data:
            logger.debug("东方财富 K 线无数据: %s", code)
            return None
        klines = data["data"].get("klines", [])
        if not klines:
            logger.debug("东方财富 K 线为空: %s", code)
            return None
        result = []
        for line in klines:
            parts = line.split(",")
            if len(parts) >= 6:
                result.append(
                    {
                        "day": parts[0],
                        "open": parts[1],
                        "close": parts[2],
                        "high": parts[3],
                        "low": parts[4],
                        "volume": parts[5],
                        "amount": parts[6] if len(parts) > 6 else "0",
                        "pct_chg": parts[8] if len(parts) > 8 else "0",
                        "source": "eastmoney",
                    }
                )
        return result if result else None
