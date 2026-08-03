"""通达信 K 线数据源（需要 pytdx 包）。

.. note::
    pytdx 不支持复权，返回不复权数据。除权日 OHLC 会跳变，
    与前复权源（eastmoney/tencent）混用会导致技术指标错误。
    因此优先级从 9 降为 2，让支持前复权的源优先命中。
"""

import logging

from common import BaseFetcher, plain_code
from common.exceptions import (
    HTTPStatusError,
    NetworkError,
    ParseError,
    RateLimitError,
)
from fetchers._common.pytdx_meta import DEFAULT_SERVERS, get_market as _get_market
from fetchers._common.pytdx_pool import HAS_PYTDX, get_default_pool

logger = logging.getLogger(__name__)

CATEGORY_MAP = {5: 0, 15: 1, 30: 2, 60: 3, 240: 9}


class PytdxKlineFetcher(BaseFetcher):
    """通达信 K 线数据源 (优先级 2) - 需要安装 pytdx 包。

    .. warning:: 不支持复权，返回不复权数据。优先级低于 eastmoney(8)/tencent(5)/sina(3)。
    """

    def __init__(self):
        super().__init__("pytdx_kline", priority=2)

    def fetch(self, code: str, **kwargs) -> list | None:
        if not HAS_PYTDX:
            return None
        scale = kwargs.get("scale", 240)
        datalen = kwargs.get("datalen", 30)
        plain = plain_code(code).zfill(6)
        market = _get_market(code)
        category = CATEGORY_MAP.get(scale, 9)
        pool = get_default_pool(DEFAULT_SERVERS)

        api, host, port = pool.get()
        success = False
        try:
            data = api.get_security_bars(category, market, plain, 0, datalen)
            if not data:
                return None
            result = []
            for d in data:
                result.append(
                    {
                        "day": str(d.get("datetime", ""))[:10],
                        "open": str(d.get("open", 0)),
                        "close": str(d.get("close", 0)),
                        "high": str(d.get("high", 0)),
                        "low": str(d.get("low", 0)),
                        "volume": str(d.get("vol", 0)),
                        "source": "pytdx",
                    }
                )
            success = True
            return result if result else None
        except (NetworkError, RateLimitError, HTTPStatusError, ParseError):
            raise  # 网络/限速/解析异常向上抛，触发熔断和退避
        except Exception as e:
            logger.debug("pytdx_kline 请求 %s:%s 失败: %s", host, port, e)
            return None
        finally:
            # P1-10: 异常时连接可能已损坏，不归还连接池避免污染后续请求
            if success:
                pool.put(api, host, port)
