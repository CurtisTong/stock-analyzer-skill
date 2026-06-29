"""通达信 K 线数据源（需要 pytdx 包）。"""

import logging

from common import BaseFetcher
from fetchers.pytdx_pool import HAS_PYTDX, get_default_pool

logger = logging.getLogger(__name__)

DEFAULT_SERVERS = [
    ("119.147.212.81", 7709),
    ("112.74.214.43", 7709),
    ("221.231.141.60", 7709),
    ("101.227.73.20", 7709),
    ("101.227.77.254", 7709),
    ("14.215.128.18", 7709),
    ("59.173.18.140", 7709),
    ("218.75.126.9", 7709),
]

CATEGORY_MAP = {5: 0, 15: 1, 30: 2, 60: 3, 240: 9}


def _get_market(code: str) -> int:
    plain = code.lstrip("shszSHSZbjBJ").zfill(6)
    if plain.startswith(("60", "68", "51", "56", "58")):
        return 1
    return 0


class PytdxKlineFetcher(BaseFetcher):
    """通达信 K 线数据源 (优先级 9) - 需要安装 pytdx 包。

    pytdx 通过通达信本地服务端口直连，速度快、无限频，是次优选择
    （最优是 sina=10）。未装 pytdx 包时此 fetcher 不会注册。
    """

    def __init__(self):
        super().__init__("pytdx_kline", priority=9)

    def fetch(self, code: str, **kwargs) -> list | None:
        if not HAS_PYTDX:
            return None
        scale = kwargs.get("scale", 240)
        datalen = kwargs.get("datalen", 30)
        plain = code.lstrip("shszSHSZbjBJ").zfill(6)
        market = _get_market(code)
        category = CATEGORY_MAP.get(scale, 9)
        pool = get_default_pool(DEFAULT_SERVERS)

        api, host, port = pool.get()
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
                    }
                )
            return result if result else None
        except Exception as e:
            logger.debug("pytdx_kline 请求 %s:%s 失败: %s", host, port, e)
            return None
        finally:
            pool.put(api, host, port)
