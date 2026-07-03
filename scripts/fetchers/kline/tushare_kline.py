"""Tushare K 线数据源（需要 tushare 包 + token）。"""

import logging
import os

from common import BaseFetcher

logger = logging.getLogger(__name__)


def _check_tushare() -> bool:
    """运行时检查 tushare 是否可用（包已安装 + token 已设置）。"""
    if not os.environ.get("TUSHARE_TOKEN"):
        return False
    try:
        import tushare  # noqa: F401

        return True
    except ImportError:
        return False


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
            plain = code.lstrip("shszSHSZbjBJ")
            if code.startswith(("sh", "SH")):
                ts_code = f"{plain}.SH"
            else:
                ts_code = f"{plain}.SZ"

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
                result.append(
                    {
                        "day": str(row.get("trade_date", "")),
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
