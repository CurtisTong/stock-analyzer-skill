"""efinance K 线数据源（需要 efinance 包）。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import BaseFetcher

try:
    import efinance as ef
    HAS_EFINANCE = True
except ImportError:
    HAS_EFINANCE = False

KLT_MAP = {5: 5, 15: 15, 30: 30, 60: 60, 240: 101}


class EfinanceKlineFetcher(BaseFetcher):
    """efinance K 线数据源 (优先级 0) - 需要安装 efinance 包。"""

    def __init__(self):
        super().__init__("efinance_kline", priority=0)

    def fetch(self, code: str, **kwargs) -> list | None:
        if not HAS_EFINANCE:
            return None
        try:
            scale = kwargs.get("scale", 240)
            datalen = kwargs.get("datalen", 30)
            plain = code.lstrip("shszSHSZbjBJ")
            klt = KLT_MAP.get(scale, 101)
            df = ef.stock.get_quote_history(plain, klt=klt, count=datalen)
            if df is None or df.empty:
                return None
            result = []
            for _, row in df.iterrows():
                result.append({
                    "day": str(row.get("日期", ""))[:10],
                    "open": str(row.get("开盘", 0)),
                    "close": str(row.get("收盘", 0)),
                    "high": str(row.get("最高", 0)),
                    "low": str(row.get("最低", 0)),
                    "volume": str(row.get("成交量", 0)),
                })
            return result if result else None
        except Exception:
            return None
