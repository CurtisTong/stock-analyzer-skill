"""通达信 K 线数据源（需要 pytdx 包）。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import BaseFetcher

try:
    from pytdx.hq import TdxHq_API
    HAS_PYTDX = True
except ImportError:
    HAS_PYTDX = False

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
    """通达信 K 线数据源 (优先级 2) - 需要安装 pytdx 包。"""

    def __init__(self):
        super().__init__("pytdx_kline", priority=2)

    def fetch(self, code: str, **kwargs) -> list | None:
        if not HAS_PYTDX:
            return None
        scale = kwargs.get("scale", 240)
        datalen = kwargs.get("datalen", 30)
        plain = code.lstrip("shszSHSZbjBJ").zfill(6)
        market = _get_market(code)
        category = CATEGORY_MAP.get(scale, 9)

        api = TdxHq_API()
        for host, port in DEFAULT_SERVERS:
            try:
                with api.connect(host, port, time_out=5):
                    data = api.get_security_bars(category, market, plain, 0, datalen)
                    if not data:
                        continue
                    result = []
                    for d in data:
                        result.append({
                            "day": str(d.get("datetime", ""))[:10],
                            "open": str(d.get("open", 0)),
                            "close": str(d.get("close", 0)),
                            "high": str(d.get("high", 0)),
                            "low": str(d.get("low", 0)),
                            "volume": str(d.get("vol", 0)),
                        })
                    return result if result else None
            except Exception:
                continue
        return None
