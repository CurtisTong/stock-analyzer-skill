"""akshare 行情数据源（需要 akshare 包）。"""

import logging
import threading
import time

from common import BaseFetcher, plain_code
from common.exceptions import (
    HTTPStatusError,
    NetworkError,
    ParseError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

try:
    import akshare as ak

    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False

# 内存缓存：同一次运行内只拉一次全量行情
# _loading 标志用于 double-checked locking：锁内只检查缓存有效性，
# 锁外做网络 IO，避免全市场拉取（数秒）期间阻塞所有并发线程。
_ak_cache = {"df": None, "ts": 0, "_loading": False}
_AK_CACHE_TTL = 60  # 秒
_ak_cache_lock = threading.Lock()


class AkshareQuoteFetcher(BaseFetcher):
    """akshare 行情数据源 (优先级 1) - 需要安装 akshare 包。"""

    def __init__(self):
        super().__init__("akshare_quote", priority=1)

    def fetch(self, code: str, **kwargs) -> dict | None:
        if not HAS_AKSHARE:
            return None
        try:
            plain = plain_code(code)

            # P1-2: double-checked locking - 锁内只检查缓存，锁外做网络 IO
            # 第一个发现缓存过期的线程做加载，其他线程发现 _loading=True 时
            # 返回 None 让 manager 切到下一源，不在此阻塞等待。
            need_load = False
            with _ak_cache_lock:
                now = time.time()
                cached_df = _ak_cache["df"]
                if cached_df is not None and (now - _ak_cache["ts"] < _AK_CACHE_TTL):
                    df = cached_df
                elif _ak_cache["_loading"]:
                    # 其他线程正在锁外加载全量行情，本线程不等待，
                    # 返回 None 让 manager 切换到下一数据源。
                    return None
                else:
                    _ak_cache["_loading"] = True
                    need_load = True

            if need_load:
                try:
                    # 锁外网络 IO：拉取全市场行情（数千行，耗时数秒）
                    df = ak.stock_zh_a_spot_em()
                except Exception:
                    # 任何异常（含 NetworkError 等可熔断异常）：清除 loading 标志后
                    # 向上抛，由外层 except 决定是触发熔断还是记录后返回 None。
                    with _ak_cache_lock:
                        _ak_cache["_loading"] = False
                    raise
                if df is None or df.empty:
                    with _ak_cache_lock:
                        _ak_cache["_loading"] = False
                    return None
                # P2-15: 以"代码"为索引，避免每次 fetch O(n) 线性扫描
                if "代码" in df.columns:
                    df = df.set_index("代码")
                with _ak_cache_lock:
                    _ak_cache["df"] = df
                    _ak_cache["ts"] = time.time()
                    _ak_cache["_loading"] = False

            # O(1) 索引查找（若未索引化则回退线性扫描）
            if df.index.name == "代码":
                try:
                    r = df.loc[plain]
                    if r is None or (hasattr(r, "empty") and r.empty):
                        return None
                except KeyError:
                    return None
            else:
                row_df = df[df["代码"] == plain]
                if row_df.empty:
                    return None
                r = row_df.iloc[0]
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
                "source": "akshare",
            }
        except (NetworkError, RateLimitError, HTTPStatusError, ParseError):
            raise  # 网络/限速/解析异常向上抛，触发熔断和退避
        except Exception as e:
            logger.debug("akshare_quote 获取失败 %s: %s", code, e)
            return None
