"""东方财富行情数据源。"""
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import BaseFetcher, http_get, to_secid, normalize_volume, normalize_amount

EASTMONEY_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f60,f116,f117,f162,f167,f168,f169,f170"


def _div100(v):
    try:
        return str(round(float(v) / 100, 2))
    except (TypeError, ValueError):
        return "0"


def _div10000(v):
    try:
        return str(round(float(v) / 100000000, 2))
    except (TypeError, ValueError):
        return "0"


class EastmoneyQuoteFetcher(BaseFetcher):
    """东方财富行情数据源 (优先级 8)。"""

    def __init__(self):
        super().__init__("eastmoney_quote", priority=8)

    def fetch(self, code: str, **kwargs) -> dict | None:
        secid = to_secid(code)
        url = EASTMONEY_QUOTE_URL.format(secid=secid)
        raw = http_get(url)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not data or data.get("rc") != 0 or "data" not in data:
            return None
        d = data["data"]
        if not d:
            return None

        code_str = str(d.get("f57", ""))
        if code_str and len(code_str) < 6:
            code_str = code_str.zfill(6)

        return {
            "code": code_str,
            "name": d.get("f58", ""),
            "price": _div100(d.get("f43", 0)),
            "prev_close": _div100(d.get("f60", 0)),
            "open": _div100(d.get("f46", 0)),
            "change_pct": _div100(d.get("f170", 0)),
            "change_amt": _div100(d.get("f169", 0)),
            "high": _div100(d.get("f44", 0)),
            "low": _div100(d.get("f45", 0)),
            "volume": normalize_volume(d.get("f47", 0), "eastmoney"),
            "amount": normalize_amount(d.get("f48", 0), "eastmoney"),
            "turnover": _div100(d.get("f168", 0)),
            "pe": _div100(d.get("f162", 0)),
            "pb": _div100(d.get("f167", 0)),
            "total_cap": _div10000(d.get("f116", 0)),
            "circulating_cap": _div10000(d.get("f117", 0)),
            "source": "eastmoney",
        }
