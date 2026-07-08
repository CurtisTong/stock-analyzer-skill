"""通达信行情数据源（需要 pytdx 包）。"""

import logging

from common import BaseFetcher, plain_code
from fetchers._common.pytdx_meta import DEFAULT_SERVERS, get_market as _get_market
from fetchers._common.pytdx_pool import HAS_PYTDX, get_default_pool

logger = logging.getLogger(__name__)


class PytdxQuoteFetcher(BaseFetcher):
    """通达信行情数据源 (优先级 9) - 需要安装 pytdx 包。

    pytdx 通过通达信本地服务端口直连，速度快、无限频，是次优选择
    （最优是 tencent=10）。未装 pytdx 包时此 fetcher 不会注册。
    """

    def __init__(self):
        super().__init__("pytdx_quote", priority=9)

    def fetch(self, code: str, **kwargs) -> dict | None:
        if not HAS_PYTDX:
            return None
        plain = plain_code(code).zfill(6)
        market = _get_market(code)
        pool = get_default_pool(DEFAULT_SERVERS)

        api, host, port = pool.get()
        try:
            data = api.get_security_quotes([(market, plain)])
            if not data:
                return None
            d = data[0]
            price = d.get("price", 0)
            prev_close = d.get("last_close", 0)
            change_pct = (
                round((price / prev_close - 1) * 100, 2) if prev_close > 0 else 0
            )
            return {
                "code": plain,
                "name": d.get("name", ""),
                "price": str(price),
                "prev_close": str(prev_close),
                "open": str(d.get("open", 0)),
                "change_pct": str(change_pct),
                "change_amt": str(round(price - prev_close, 2)),
                "high": str(d.get("high", 0)),
                "low": str(d.get("low", 0)),
                "volume": str(d.get("vol", 0)),
                "amount": str(d.get("amount", 0)),
                "turnover": "",
                "pe": "",
                "pb": "",
                "total_cap": "",
                "circulating_cap": "",
            }
        except Exception as e:
            logger.debug("pytdx_quote 请求 %s:%s 失败: %s", host, port, e)
            return None
        finally:
            pool.put(api, host, port)
