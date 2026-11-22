"""雪球行情数据源。"""

import logging


from common import BaseFetcher, NOT_HANDLED, http_get_with_headers, plain_code, to_float
from common.exceptions.silent_fallback import log_silent_fallback

logger = logging.getLogger(__name__)

# 雪球行情 API
XUEQIU_URL = "https://stock.xueqiu.com/v5/stock/quote.json?symbol={symbol}&extend=detail"


def _to_xueqiu_symbol(code: str) -> str:
    """转换为雪球代码格式：600989.SH / SH600989 / 600989 -> SH600989。

    P1-12 (2026-11-21 review §3.1 #12)：
    - 支持 ``.SH/.SZ/.BJ`` 后缀（此前 600989.SH → SH600989.SH，雪球必然失败）；
    - ``us:/hk:`` 跨市场代码返回 NOT_HANDLED，交由 yfinance 等专门源处理。
    """
    raw = str(code or "").strip()
    if raw.lower().startswith(("us:", "hk:")):
        return NOT_HANDLED
    c = raw.upper()
    # 去后缀：600989.SH / 000001.SZ / 430047.BJ
    # BJ 必须保留为前缀（雪球北交所代码形如 BJ430047），不能按数字段误判成深市。
    if "." in c:
        stem, _, suffix = c.partition(".")
        if suffix in ("SH", "SZ", "BJ"):
            return f"{suffix}{stem}"
    if c.startswith(("SH", "SZ", "BJ")):
        return c
    # 纯数字代码：6 开头沪市，其余深市（与项目其它 fetcher 一致的简化口径）
    return f"SH{c}" if c.startswith("6") else f"SZ{c}"


def _parse_quote(data: dict, expected_symbol: str = "") -> dict | None:
    """解析雪球行情数据；expected_symbol 非空时校验返回 code 一致（P1-12）。"""
    if not data or "data" not in data:
        return None
    quote = data.get("data", {}).get("quote")
    if not quote:
        return None
    returned = str(quote.get("symbol", "") or "")
    # P1-12：雪偶发返回别的标的/空 code，不能静默落到下游污染缓存与展示。
    if expected_symbol and (not returned or plain_code(returned) != plain_code(expected_symbol)):
        logger.debug("雪球行情 code 不匹配，跳过: 请求=%s 返回=%s", expected_symbol, returned)
        return None
    return {
        "code": returned,
        "name": quote.get("name", ""),
        "price": to_float(quote.get("current")),
        "open": to_float(quote.get("open")),
        "high": to_float(quote.get("high")),
        "low": to_float(quote.get("low")),
        "prev_close": to_float(quote.get("last_close")),
        "volume": to_float(quote.get("volume")),
        "amount": to_float(quote.get("amount")),
        "turnover": to_float(quote.get("turnover_rate")),
        "pe": to_float(quote.get("pe_ttm")),
        "pe_type": "ttm",  # pe_ttm 为滚动市盈率
        "pb": to_float(quote.get("pb")),
        "total_cap": to_float(quote.get("market_capital")),  # 原始元值，归一化在 data 层
        "circulating_cap": to_float(quote.get("float_market_capital")),
        "source": "xueqiu",
    }


class XueqiuQuoteFetcher(BaseFetcher):
    """雪球行情数据源 (优先级 8)。"""

    def __init__(self):
        super().__init__("xueqiu_quote", priority=8)

    def fetch(self, code: str, **kwargs) -> dict | None:
        symbol = _to_xueqiu_symbol(code)
        # P1-12：跨市场代码本源不处理，返回哨兵让 manager 跳过（记 not_handled 血缘）
        if symbol is NOT_HANDLED:
            return NOT_HANDLED
        url = XUEQIU_URL.format(symbol=symbol)
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://xueqiu.com/",
            "Origin": "https://xueqiu.com",
        }
        try:
            raw = http_get_with_headers(url, headers=headers, timeout=self.timeout)
            import json

            data = json.loads(raw)
            return _parse_quote(data, expected_symbol=symbol)  # P1-12：校验返回 code
        except Exception as e:
            log_silent_fallback("xueqiu_quote.fetch", e)
            logger.debug("xueqiu_quote 获取失败 %s: %s", code, e)
            return None
