"""efinance 行情数据源（需要 efinance 包）。"""

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
    import efinance as ef

    HAS_EFINANCE = True
except ImportError:
    HAS_EFINANCE = False

# 内存缓存：同一次运行内只拉一次全量行情（避免重复请求）
# _loading 标志用于 double-checked locking：锁内只检查缓存有效性，
# 锁外做网络 IO，避免全市场拉取（数秒）期间阻塞所有并发线程。
_ef_cache = {"df": None, "ts": 0, "_loading": False}
_EF_CACHE_TTL = 60  # 秒
_ef_cache_lock = threading.Lock()


class EfinanceQuoteFetcher(BaseFetcher):
    """efinance 行情数据源 (优先级 0) - 需要安装 efinance 包。"""

    def __init__(self):
        super().__init__("efinance_quote", priority=0)

    def fetch(self, code: str, **kwargs) -> dict | None:
        if not HAS_EFINANCE:
            return None
        try:
            # efinance 接受纯代码如 "600989"
            plain = plain_code(code)

            # P1-2: double-checked locking - 锁内只检查缓存，锁外做网络 IO
            # 第一个发现缓存过期的线程做加载，其他线程发现 _loading=True 时
            # 返回 None 让 manager 切到下一源，不在此阻塞等待。
            need_load = False
            with _ef_cache_lock:
                now = time.time()
                cached_df = _ef_cache["df"]
                if cached_df is not None and (now - _ef_cache["ts"] < _EF_CACHE_TTL):
                    df = cached_df
                elif _ef_cache["_loading"]:
                    # 其他线程正在锁外加载全量行情，本线程不等待，
                    # 返回 None 让 manager 切换到下一数据源。
                    return None
                else:
                    _ef_cache["_loading"] = True
                    need_load = True

            if need_load:
                try:
                    # 锁外网络 IO：拉取全市场行情（数千行，耗时数秒）
                    df = ef.stock.get_realtime_quotes()
                except Exception:
                    # 任何异常（含 NetworkError 等可熔断异常）：清除 loading 标志后
                    # 向上抛，由外层 except 决定是触发熔断还是记录后返回 None。
                    with _ef_cache_lock:
                        _ef_cache["_loading"] = False
                    raise
                if df is None or df.empty:
                    with _ef_cache_lock:
                        _ef_cache["_loading"] = False
                    return None
                with _ef_cache_lock:
                    _ef_cache["df"] = df
                    _ef_cache["ts"] = time.time()
                    _ef_cache["_loading"] = False

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
                "pe_type": "dynamic",  # 市盈率-动态
                "pb": str(r.get("市净率", 0)),
                "total_cap": str(r.get("总市值", 0)),  # 原始元值，归一化在 data 层
                "circulating_cap": str(r.get("流通市值", 0)),
                "source": "efinance",
            }
        except (NetworkError, RateLimitError, HTTPStatusError, ParseError):
            raise  # 网络/限速/解析异常向上抛，触发熔断和退避
        except Exception as e:
            logger.debug("efinance_quote 获取失败 %s: %s", code, e)
            return None
