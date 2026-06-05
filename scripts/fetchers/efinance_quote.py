"""efinance 行情数据源（需要 efinance 包）。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import BaseFetcher

try:
    import efinance as ef
    HAS_EFINANCE = True
except ImportError:
    HAS_EFINANCE = False


class EfinanceQuoteFetcher(BaseFetcher):
    """efinance 行情数据源 (优先级 0) - 需要安装 efinance 包。"""

    def __init__(self):
        super().__init__("efinance_quote", priority=0)

    def fetch(self, code: str, **kwargs) -> dict | None:
        if not HAS_EFINANCE:
            return None
        try:
            # efinance 接受纯代码如 "600989"
            plain = code.lstrip("shszSHSZbjBJ")
            df = ef.stock.get_realtime_quotes()
            if df is None or df.empty:
                return None
            row = df[df["股票代码"] == plain]
            if row.empty:
                return None
            r = row.iloc[0]
            return {
                "code": str(r.get("股票代码", "")),
                "name": str(r.get("股票名称", "")),
                "price": str(r.get("最新价", 0)),
                "prev_close": str(r.get("昨收", 0)),
                "open": str(r.get("今开", 0)),
                "change_pct": str(r.get("涨跌幅", 0)),
                "change_amt": str(r.get("涨跌额", 0)),
                "high": str(r.get("最高", 0)),
                "low": str(r.get("最低", 0)),
                "volume": str(r.get("成交量", 0)),
                "amount": str(r.get("成交额", 0)),
                "turnover": str(r.get("换手率", 0)),
                "pe": str(r.get("市盈率-动态", 0)),
                "pb": str(r.get("市净率", 0)),
                "total_cap": str(r.get("总市值", 0)),
                "circulating_cap": str(r.get("流通市值", 0)),
            }
        except Exception:
            return None
