"""Yahoo Finance K 线数据源（需要 yfinance 包）。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import BaseFetcher

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False


def _to_yf_symbol(code: str) -> str:
    """转换为 yfinance 符号格式。"""
    plain = code.lstrip("shszSHSZbjBJ").zfill(6)
    if plain.startswith(("60", "68", "51", "56", "58")):
        return f"{plain}.SS"
    elif plain.startswith(("00", "30", "15", "16", "18")):
        return f"{plain}.SZ"
    elif plain.startswith(("43", "83", "87", "88", "92")):
        return f"{plain}.BJ"
    return code


class YfinanceKlineFetcher(BaseFetcher):
    """Yahoo Finance K 线数据源 (优先级 4) - 需要安装 yfinance 包。"""

    def __init__(self):
        super().__init__("yfinance_kline", priority=4)

    def fetch(self, code: str, **kwargs) -> list | None:
        if not HAS_YFINANCE:
            return None
        try:
            scale = kwargs.get("scale", 240)
            datalen = kwargs.get("datalen", 30)
            symbol = _to_yf_symbol(code)

            ticker = yf.Ticker(symbol)
            if scale == 240:
                df = ticker.history(period=f"{datalen}d")
            elif scale == 60:
                df = ticker.history(period="60d", interval="1h")
            elif scale == 5:
                df = ticker.history(period="5d", interval="5m")
            else:
                df = ticker.history(period=f"{datalen}d")

            if df is None or df.empty:
                return None

            result = []
            for idx, row in df.iterrows():
                result.append({
                    "day": str(idx)[:10],
                    "open": str(round(row.get("Open", 0), 2)),
                    "close": str(round(row.get("Close", 0), 2)),
                    "high": str(round(row.get("High", 0), 2)),
                    "low": str(round(row.get("Low", 0), 2)),
                    "volume": str(int(row.get("Volume", 0))),
                })
            return result if result else None
        except Exception:
            return None
