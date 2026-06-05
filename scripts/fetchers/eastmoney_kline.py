"""东方财富 K 线数据源。"""
import sys
import json
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import BaseFetcher

EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get?cb=&secid={secid}&ut=fa5fd1943c7b386f172d6893dbbd4dc1&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt={klt}&fqt=1&end=20500101&lmt={lmt}"
KLT_MAP = {5: 5, 15: 15, 30: 30, 60: 60, 240: 101}


def _to_secid(code: str) -> str:
    c = code.strip().lower()
    if c.startswith("sh"):
        return f"1.{c[2:]}"
    if c.startswith("sz"):
        return f"0.{c[2:]}"
    plain = c.lstrip("shszbj")
    if plain.startswith(("60", "68", "51", "56", "58")):
        return f"1.{plain}"
    return f"0.{plain}"


class EastmoneyKlineFetcher(BaseFetcher):
    """东方财富 K 线数据源 (优先级 8)。"""

    def __init__(self):
        super().__init__("eastmoney_kline", priority=8)

    def fetch(self, code: str, **kwargs) -> list | None:
        scale = kwargs.get("scale", 240)
        datalen = kwargs.get("datalen", 30)
        secid = _to_secid(code)
        klt = KLT_MAP.get(scale, 101)
        url = EASTMONEY_KLINE_URL.format(secid=secid, klt=klt, lmt=datalen)
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://quote.eastmoney.com/",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not data or data.get("rc") != 0 or "data" not in data:
            return None
        klines = data["data"].get("klines", [])
        if not klines:
            return None
        result = []
        for line in klines:
            parts = line.split(",")
            if len(parts) >= 6:
                result.append({
                    "day": parts[0],
                    "open": parts[1],
                    "close": parts[2],
                    "high": parts[3],
                    "low": parts[4],
                    "volume": parts[5],
                })
        return result if result else None
