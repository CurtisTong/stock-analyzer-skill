"""雪球行情数据源。"""

import logging
from pathlib import Path


from common import BaseFetcher, http_get_with_headers, to_float

logger = logging.getLogger(__name__)

# 雪球行情 API
XUEQIU_URL = (
    "https://stock.xueqiu.com/v5/stock/quote.json?symbol={symbol}&extend=detail"
)


def _to_xueqiu_symbol(code: str) -> str:
    """转换为雪球代码格式：SH600989 -> SH600989。"""
    code = code.strip().upper()
    if code.startswith(("SH", "SZ")):
        return code
    # 纯数字代码
    if code.startswith("6"):
        return f"SH{code}"
    return f"SZ{code}"


def _parse_quote(data: dict) -> dict | None:
    """解析雪球行情数据。"""
    if not data or "data" not in data:
        return None
    quote = data.get("data", {}).get("quote")
    if not quote:
        return None
    return {
        "code": quote.get("symbol", ""),
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
        "pb": to_float(quote.get("pb")),
        "total_cap": round(to_float(quote.get("market_capital")) / 1e8, 2),
        "circulating_cap": 0,
        "source": "xueqiu",
    }


class XueqiuQuoteFetcher(BaseFetcher):
    """雪球行情数据源 (优先级 8)。"""

    def __init__(self):
        super().__init__("xueqiu_quote", priority=8)

    def fetch(self, code: str, **kwargs) -> dict | None:
        symbol = _to_xueqiu_symbol(code)
        url = XUEQIU_URL.format(symbol=symbol)
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://xueqiu.com/",
            "Origin": "https://xueqiu.com",
        }
        try:
            raw = http_get_with_headers(url, headers=headers, timeout=10)
            import json

            data = json.loads(raw)
            return _parse_quote(data)
        except Exception as e:
            logger.debug("xueqiu_quote 获取失败 %s: %s", code, e)
            return None
