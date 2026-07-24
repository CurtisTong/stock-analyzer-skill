"""Yahoo Finance 美股/港股行情数据源（需要 yfinance 包）。

处理 us: 前缀的美股代码（如 us:^gspc、us:spy）和 hk: 前缀的港股代码（如 hk:0700、hk:00700），
A 股代码返回 NOT_HANDLED 不干扰现有链路。
"""

import logging

from common import BaseFetcher, NOT_HANDLED, RateLimitError

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
except ImportError:
    yf = None

# yfinance 限流异常（不同版本可能缺失，缺失时置 Exception 兜底，由通用 except 记录）
try:
    from yfinance.exceptions import YFRateLimitError
except ImportError:
    YFRateLimitError = ()  # 空元组使 except 子句匹配任何异常为 False，等价于跳过

# 跨市场代码前缀
US_PREFIX = "us:"
HK_PREFIX = "hk:"


def _is_cross_market_code(code: str) -> bool:
    """判断是否为 us:/hk: 前缀的跨市场代码（大小写无关）。"""
    c = code.lower()
    return c.startswith(US_PREFIX) or c.startswith(HK_PREFIX)


def _to_yf_symbol(code: str) -> str | None:
    """从 us:/hk: 前缀代码提取 yfinance 符号。

    us:^gspc -> ^gspc, us:spy -> spy, US:SPY -> spy
    hk:0700 -> 0700.HK, hk:00700 -> 0700.HK, HK:09988 -> 9988.HK
    返回 None 表示符号为空（如输入 'us:'）。
    """
    c = code.lower()
    _, _, symbol = code.partition(":")
    symbol = symbol.strip()
    if not symbol:
        return None
    # 港股：补 5 位 + .HK 后缀（yfinance 港股格式 0700.HK）
    if c.startswith(HK_PREFIX):
        digits = symbol.lstrip("0")
        # yfinance 接受 4 位（0700）或带前导零，统一补齐 4 位
        padded = digits.zfill(4)
        return f"{padded}.HK"
    # 美股：原样返回（保留 ^ 等特殊字符）
    return symbol


class YfinanceQuoteFetcher(BaseFetcher):
    """Yahoo Finance 美股/港股行情数据源 (优先级 6) - 需要安装 yfinance 包。

    处理 us: 前缀（美股）和 hk: 前缀（港股）代码，不处理 A 股，避免干扰国内数据源链路。
    """

    def __init__(self):
        super().__init__("yfinance_quote", priority=6)

    def fetch(self, code: str, **kwargs) -> dict | None:
        if yf is None:
            return NOT_HANDLED
        if not _is_cross_market_code(code):
            return NOT_HANDLED

        try:
            symbol = _to_yf_symbol(code)
            if not symbol:
                return None
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}

            if not info or info.get("regularMarketPrice") is None:
                # 回退：从最近 K 线取收盘价
                hist = ticker.history(period="2d")
                if hist is None or hist.empty:
                    return None
                last = hist.iloc[-1]
                prev = hist.iloc[-2] if len(hist) > 1 else last
                price = float(last["Close"])
                prev_close = float(prev["Close"])
                change_amt = price - prev_close
                change_pct = (change_amt / prev_close * 100) if prev_close else 0
                return {
                    "code": code,
                    "name": info.get("shortName", symbol),
                    "price": str(round(price, 2)),
                    "prev_close": str(round(prev_close, 2)),
                    "open": str(round(float(last.get("Open", 0)), 2)),
                    "high": str(round(float(last.get("High", 0)), 2)),
                    "low": str(round(float(last.get("Low", 0)), 2)),
                    "change_pct": str(round(change_pct, 2)),
                    "change_amt": str(round(change_amt, 2)),
                    "volume": str(int(last.get("Volume", 0))),
                    "amount": "0",
                    "turnover": "0",
                    "pe": str(info.get("trailingPE", 0) or 0),
                    "pb": str(info.get("priceToBook", 0) or 0),
                    "total_cap": str(round((info.get("marketCap", 0) or 0) / 1e8, 2)),
                    "circulating_cap": "0",
                    "source": "yfinance",
                }

            price = info["regularMarketPrice"]
            prev_close = info.get("regularMarketPreviousClose", 0) or 0
            change_amt = price - prev_close if prev_close else 0
            change_pct = info.get("regularMarketChangePercent", 0) or 0

            return {
                "code": code,
                "name": info.get("shortName", symbol),
                "price": str(round(price, 2)),
                "prev_close": str(round(prev_close, 2)),
                "open": str(round(info.get("regularMarketOpen", 0) or 0, 2)),
                "high": str(round(info.get("regularMarketDayHigh", 0) or 0, 2)),
                "low": str(round(info.get("regularMarketDayLow", 0) or 0, 2)),
                "change_pct": str(round(change_pct, 2)),
                "change_amt": str(round(change_amt, 2)),
                "volume": str(int(info.get("regularMarketVolume", 0) or 0)),
                "amount": "0",
                "turnover": "0",
                "pe": str(info.get("trailingPE", 0) or 0),
                "pb": str(info.get("priceToBook", 0) or 0),
                "total_cap": str(round((info.get("marketCap", 0) or 0) / 1e8, 2)),
                "circulating_cap": "0",
                "source": "yfinance",
            }
        except YFRateLimitError as e:
            # 转译为项目 RateLimitError，触发 DataFetcherManager 的 429 退避 + 重试主源链路
            raise RateLimitError(url=f"yfinance:{symbol}", retry_after=60) from e
        except RateLimitError:
            # 由 YFRateLimitError 转译而来，直接向上抛
            raise
        except Exception as e:
            logger.debug("yfinance_quote 获取失败 %s: %s", code, e)
            return None
