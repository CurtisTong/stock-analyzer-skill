"""Yahoo Finance 美股行情数据源（需要 yfinance 包）。

仅处理 us: 前缀的美股代码（如 us:^gspc、us:spy），A 股代码返回 NOT_HANDLED 不干扰现有链路。
"""
import logging
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import BaseFetcher, NOT_HANDLED

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
except ImportError:
    yf = None

# 美股代码前缀
US_PREFIX = "us:"


def _is_us_code(code: str) -> bool:
    """判断是否为 us: 前缀的美股代码（大小写无关）。"""
    return code.lower().startswith(US_PREFIX)


def _to_yf_symbol(code: str) -> str | None:
    """从 us: 前缀代码提取 yfinance 符号。

    us:^gspc → ^gspc, us:spy → spy, US:SPY → spy
    返回 None 表示符号为空（如输入 'us:'）。
    """
    # 按第一个冒号分割，取符号部分（大小写无关）
    _, _, symbol = code.partition(":")
    symbol = symbol.strip()
    return symbol if symbol else None


class YfinanceQuoteFetcher(BaseFetcher):
    """Yahoo Finance 美股行情数据源 (优先级 6) - 需要安装 yfinance 包。

    仅处理 us: 前缀代码，不处理 A 股，避免干扰国内数据源链路。
    """

    def __init__(self):
        super().__init__("yfinance_quote", priority=6)

    def fetch(self, code: str, **kwargs) -> dict | None:
        if yf is None:
            return NOT_HANDLED
        if not _is_us_code(code):
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
        except Exception as e:
            logger.debug("yfinance_quote 获取失败 %s: %s", code, e)
            return None
