"""Tushare K 线数据源（需要 tushare 包 + token）。"""

import logging
import os

from common import BaseFetcher, plain_code, infer_exchange
from fetchers._common.tushare_check import check_tushare as _check_tushare

logger = logging.getLogger(__name__)


class TushareKlineFetcher(BaseFetcher):
    """Tushare K 线数据源 (优先级 2) - 需要安装 tushare 包并设置 TUSHARE_TOKEN。"""

    def __init__(self):
        super().__init__("tushare_kline", priority=2)

    def fetch(self, code: str, **kwargs) -> list | None:
        if not _check_tushare():
            return None
        try:
            import tushare as ts

            token = os.environ.get("TUSHARE_TOKEN", "")
            if token:
                ts.set_token(token)

            scale = kwargs.get("scale", 240)
            datalen = kwargs.get("datalen", 30)
            plain = plain_code(code)
            ex = infer_exchange(code)  # "sh"/"sz"/"bj"，按代码段推断而非硬编码
            ts_code = f"{plain}.{ex.upper()}" if ex else f"{plain}.SZ"

            pro = ts.pro_api()
            if scale == 240:
                df = pro.daily(ts_code=ts_code, limit=datalen)
            else:
                # 分钟线需要额外权限
                return None

            if df is None or df.empty:
                return None

            result = []
            for _, row in df.iterrows():
                # tushare trade_date 为 YYYYMMDD（如 "20260108"），统一为 YYYY-MM-DD
                td = str(row.get("trade_date", ""))
                day = f"{td[:4]}-{td[4:6]}-{td[6:8]}" if len(td) == 8 else td
                result.append(
                    {
                        "day": day,
                        "open": str(row.get("open", 0)),
                        "close": str(row.get("close", 0)),
                        "high": str(row.get("high", 0)),
                        "low": str(row.get("low", 0)),
                        "volume": str(row.get("vol", 0)),
                        "source": "tushare",
                    }
                )
            result.reverse()  # tushare 返回倒序
            return result if result else None
        except Exception as e:
            logger.debug("tushare_kline 获取失败 %s: %s", code, e)
            return None
