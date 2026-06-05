"""Baostock K 线数据源（需要 baostock 包）。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import BaseFetcher

try:
    import baostock as bs
    HAS_BAOSTOCK = True
except ImportError:
    HAS_BAOSTOCK = False


class BaostockKlineFetcher(BaseFetcher):
    """Baostock K 线数据源 (优先级 3) - 需要安装 baostock 包。"""

    def __init__(self):
        super().__init__("baostock_kline", priority=3)

    def fetch(self, code: str, **kwargs) -> list | None:
        if not HAS_BAOSTOCK:
            return None
        scale = kwargs.get("scale", 240)
        datalen = kwargs.get("datalen", 30)

        # baostock 格式: sh.600989
        plain = code.lstrip("shszSHSZbjBJ").zfill(6)
        if plain.startswith(("60", "68", "51", "56", "58")):
            bs_code = f"sh.{plain}"
        else:
            bs_code = f"sz.{plain}"

        if scale != 240:
            return None  # baostock 只支持日线

        try:
            lg = bs.login()
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume",
                count=datalen,
                frequency="d",
                adjustflag="2",
            )
            if rs.error_code != "0":
                bs.logout()
                return None
            result = []
            while rs.next():
                row = rs.get_row_data()
                if len(row) >= 6:
                    result.append({
                        "day": row[0],
                        "open": row[1],
                        "high": row[2],
                        "low": row[3],
                        "close": row[4],
                        "volume": row[5],
                    })
            bs.logout()
            return result if result else None
        except Exception:
            return None
