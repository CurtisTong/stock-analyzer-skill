"""通达信行情数据源（需要 pytdx 包）。"""

import logging
from typing import Any

from common import BaseFetcher, plain_code
from common.exceptions import (
    HTTPStatusError,
    NetworkError,
    ParseError,
    RateLimitError,
)
from fetchers._common.pytdx_meta import DEFAULT_SERVERS, get_market as _get_market
from fetchers._common.pytdx_pool import HAS_PYTDX, get_default_pool
from fetchers._common.pytdx_probe import any_server_available

logger = logging.getLogger(__name__)


class PytdxQuoteFetcher(BaseFetcher):
    """通达信行情数据源 - 需要安装 pytdx 包。

    pytdx 通过通达信本地服务端口直连，速度快、无限频，是次优选择
    （最优是 tencent=10）。未装 pytdx 包时此 fetcher 不会注册。

    .. note::
        失败语义与 pytdx_kline 保持一致：连接/请求异常向上抛，
        触发熔断器与退避。原实现把异常吞成 None，manager 记为
        "empty（无数据）"而非失败 → 熔断器永不开启，而连接池会
        依次尝试 8 个服务器 × 5s（最坏 ~40s 阻塞）且每次请求重复。
    """

    def __init__(self):
        super().__init__("pytdx_quote", priority=4)

    def fetch(self, code: str, **kwargs) -> dict | None:
        if not HAS_PYTDX:
            return None
        # 探活：本地/局域网没有通达信服务时直接跳过。
        # 这不是"数据源故障"，而是环境缺能力——不应进入降级链污染血缘，
        # 也不应让熔断器去累计一个永远不会自愈的失败。
        if not any_server_available(DEFAULT_SERVERS):
            logger.debug("pytdx_quote: 无可用通达信服务，跳过")
            return None
        plain = plain_code(code).zfill(6)
        market = _get_market(code)
        pool = get_default_pool(DEFAULT_SERVERS)

        api: Any = None
        host = ""
        port = 0
        success = False
        try:
            api, host, port = pool.get()
            data = api.get_security_quotes([(market, plain)])
            if not data:
                return None
            d = data[0]
            price = d.get("price", 0)
            prev_close = d.get("last_close", 0)
            change_pct = round((price / prev_close - 1) * 100, 2) if prev_close > 0 else 0
            success = True
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
                "source": "pytdx",
            }
        except (NetworkError, RateLimitError, HTTPStatusError, ParseError):
            raise  # 网络/限速/解析异常向上抛，触发熔断和退避
        except Exception as e:
            # 连接池全部服务器不可用（RuntimeError）等异常：必须按失败上报，
            # 否则熔断器不会累计失败次数，pytdx 会在每次请求时重复 8×5s 阻塞。
            logger.warning("pytdx_quote 请求 %s:%s 失败: %s", host, port, e)
            raise NetworkError(f"pytdx_quote {code}", str(e)) from e
        finally:
            # 异常时连接可能已损坏，不归还连接池避免污染后续请求
            if success and api is not None:
                pool.put(api, host, port)
