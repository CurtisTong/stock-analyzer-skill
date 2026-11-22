"""新浪 K 线数据源。

.. note::
    新浪 API 不支持复权参数，返回不复权数据。除权日 OHLC 会跳变，
    与前复权源（eastmoney/tencent）混用会导致技术指标错误。
    P0-2 (2026-11-21 review §2)：原 YAML 配置 priority=10（全源最高）与本模块
    注释及代码默认值相互矛盾，导致默认配置下优先取不复权数据。现已将 YAML 与
    代码默认值统一降为 0（全源最低），仅作为最后兜底；返回的 records 显式带
    ``adjust="none"``，由 data 层写入 KlineBar.adjust，供下游识别口径。
"""

import json

from common import BaseFetcher, http_get
from common.exceptions import (
    HTTPStatusError,
    NetworkError,
    ParseError,
    RateLimitError,
)

# 新浪 K 线接口（与 quote 的 hq.sinajs.cn 不同，走 quotes_service）。
# 查询参数：
#   symbol   股票代码（带交易所前缀，如 sh600989）
#   scale    K 线周期（分钟）：240=日线, 60=60分钟, 30=30分钟, 5=5分钟...
#   ma=no    不返回均线数据（本项目自行计算 MA）
#   datalen  返回 K 线根数（上限约 1023，超出返回空）
SINA_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale={scale}&ma=no&datalen={datalen}"


class SinaKlineFetcher(BaseFetcher):
    """新浪 K 线数据源 (优先级 0，最后兜底)。

    .. warning:: 不支持复权，返回不复权数据（adjust="none"）。优先级低于
       eastmoney(8)/tencent(6) 等所有前复权源；仅当其它源全部失败才命中。
       P0-2：此默认值与 data_source.yaml 的 kline_sources.sina.priority 保持一致。
    """

    def __init__(self):
        super().__init__("sina_kline", priority=0)

    def fetch(self, code: str, **kwargs) -> list | None:
        scale = kwargs.get("scale", 240)
        datalen = kwargs.get("datalen", 30)
        # 新浪 API datalen 上限约 1023，超出返回空
        datalen = min(int(datalen), 1023)
        timeout = kwargs.get("timeout", self.timeout)
        raw = http_get(
            SINA_URL.format(symbol=code, scale=scale, datalen=datalen),
            timeout=timeout,
            max_retries=self.retry,
        )
        try:
            records = json.loads(raw)
            if records:
                for r in records:
                    r["source"] = "sina"
                    # P0-2：显式标注不复权口径，data 层写入 KlineBar.adjust
                    r["adjust"] = "none"
                return records
            return None
        except (NetworkError, RateLimitError, HTTPStatusError, ParseError):
            raise  # 网络/限速/解析异常向上抛，触发熔断和退避
        except json.JSONDecodeError as e:
            # review §4.1 P2：反爬 HTML 错误页/接口改版返回非 JSON 时，
            # 不能再当“无数据”（记 empty、不熔断），否则会持续高频打失效源。
            # 与 eastmoney/tencent kline 的 ParseError 口径统一。
            preview = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
            raise ParseError(preview, "sina_kline", str(e)) from e
