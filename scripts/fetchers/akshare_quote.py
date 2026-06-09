"""akshare 行情数据源（需要 akshare 包）。"""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import BaseFetcher

try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False

# 内存缓存：同一次运行内只拉一次全量行情
_ak_cache = {"df": None, "ts": 0}
_AK_CACHE_TTL = 60  # 秒


class AkshareQuoteFetcher(BaseFetcher):
    """akshare 行情数据源 (优先级 1) - 需要安装 akshare 包。"""

    def __init__(self):
        super().__init__("akshare_quote", priority=1)

    def fetch(self, code: str, **kwargs) -> dict | None:
        if not HAS_AKSHARE:
            return None
        try:
            plain = code.lstrip("shszSHSZbjBJ")

            # 使用内存缓存避免重复拉取全量数据
            now = time.time()
            if _ak_cache["df"] is None or now - _ak_cache["ts"] > _AK_CACHE_TTL:
                df = ak.stock_zh_a_spot_em()
                if df is None or df.empty:
                    return None
                _ak_cache["df"] = df
                _ak_cache["ts"] = now
            else:
                df = _ak_cache["df"]

            row = df[df["代码"] == plain]
            if row.empty:
                return None
            r = row.iloc[0]
            return {
                "code": str(r.get("代码", "")),
                "name": str(r.get("名称", "")),
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
