"""akshare K 线数据源（需要 akshare 包）。"""

import logging

from common import BaseFetcher, plain_code
from common.exceptions import (
    HTTPStatusError,
    NetworkError,
    ParseError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

try:
    import akshare as ak

    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False


def _pick_col(df, candidates: tuple[str, ...]) -> str | None:
    """从 DataFrame 列名中按候选顺序取第一个存在的列。

    akshare 版本更新可能变更列名（如"日期"->"交易日"），用此做容错。
    """
    cols = set(df.columns)
    for c in candidates:
        if c in cols:
            return c
    return None


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
            plain = plain_code(code)

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
            # 列名容错：akshare 版本更新可能变更列名（P1-4）
            col_day = _pick_col(df, ("日期", "交易日", "date"))
            col_open = _pick_col(df, ("开盘", "open"))
            col_close = _pick_col(df, ("收盘", "close"))
            col_high = _pick_col(df, ("最高", "high"))
            col_low = _pick_col(df, ("最低", "low"))
            col_volume = _pick_col(df, ("成交量", "volume"))
            if not col_day:
                logger.warning(
                    "akshare 日线列名变动: 缺日期列，实际列=%s", list(df.columns)
                )
                return None
            result = []
            for _, row in df.iterrows():
                result.append(
                    {
                        "day": str(row.get(col_day, ""))[:10],
                        "open": str(row.get(col_open, 0)),
                        "close": str(row.get(col_close, 0)),
                        "high": str(row.get(col_high, 0)),
                        "low": str(row.get(col_low, 0)),
                        "volume": str(row.get(col_volume, 0)),
                        "source": "akshare",
                    }
                )
            return result if result else None
        except (NetworkError, RateLimitError, HTTPStatusError, ParseError):
            raise  # 网络/限速/解析异常向上抛，触发熔断和退避
        except Exception as e:
            logger.debug("akshare_kline 获取失败 %s: %s", code, e)
            return None
