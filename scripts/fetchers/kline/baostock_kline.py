"""Baostock K 线数据源（需要 baostock 包）。

模块级一次性 login/logout，避免每次 fetch 都握手。
"""

import atexit
import logging
import threading


from common import BaseFetcher, plain_code
from common.exceptions import (
    HTTPStatusError,
    NetworkError,
    ParseError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

try:
    import baostock as bs

    HAS_BAOSTOCK = True
except ImportError:
    HAS_BAOSTOCK = False

# 模块级登录锁，确保只 login 一次
_bs_login_lock = threading.Lock()
_bs_logged_in = False


def _ensure_logged_in():
    """确保 baostock 已登录（线程安全，双检锁防止并发重复 login）。

    login 失败时抛 RuntimeError，由调用方捕获（不再静默继续用未登录状态发请求）。
    """
    global _bs_logged_in
    # 快速路径：已登录则直接返回（锁外读，GIL 兜底可见性）
    if _bs_logged_in:
        return
    with _bs_login_lock:
        if _bs_logged_in:  # 双检锁：防止并发重复 login
            return
        try:
            lg = bs.login()
            if lg.error_code != "0":
                raise RuntimeError(f"baostock login 失败: {lg.error_msg}")
            _bs_logged_in = True
        except (NetworkError, RateLimitError, HTTPStatusError, ParseError):
            raise  # 网络/限速/解析异常向上抛，触发熔断和退避
        except Exception as e:
            raise RuntimeError(f"baostock login 异常: {e}") from e


def _logout():
    """进程退出时 logout。"""
    global _bs_logged_in
    if _bs_logged_in:
        try:
            bs.logout()
        except (NetworkError, RateLimitError, HTTPStatusError, ParseError):
            raise  # 网络/限速/解析异常向上抛，触发熔断和退避
        except Exception as e:
            logger.debug("baostock logout 失败: %s", e)
        _bs_logged_in = False


if HAS_BAOSTOCK:
    atexit.register(_logout)


class BaostockKlineFetcher(BaseFetcher):
    """Baostock K 线数据源 (优先级 1) - 需要安装 baostock 包。"""

    def __init__(self):
        super().__init__("baostock_kline", priority=1)

    def fetch(self, code: str, **kwargs) -> list | None:
        if not HAS_BAOSTOCK:
            return None
        scale = kwargs.get("scale", 240)
        datalen = kwargs.get("datalen", 30)

        if scale != 240:
            return None  # baostock 只支持日线

        # baostock 格式: sh.600989
        plain = plain_code(code).zfill(6)
        if plain.startswith(("60", "68", "51", "56", "58")):
            bs_code = f"sh.{plain}"
        else:
            bs_code = f"sz.{plain}"

        try:
            _ensure_logged_in()
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume",
                count=datalen,
                frequency="d",
                adjustflag="2",
            )
            if rs.error_code != "0":
                return None
            result = []
            while rs.next():
                row = rs.get_row_data()
                if len(row) >= 6:
                    result.append(
                        {
                            "day": row[0],
                            "open": row[1],
                            "high": row[2],
                            "low": row[3],
                            "close": row[4],
                            "volume": row[5],
                            "source": "baostock",
                        }
                    )
            return result if result else None
        except (NetworkError, RateLimitError, HTTPStatusError, ParseError):
            raise  # 网络/限速/解析异常向上抛，触发熔断和退避
        except Exception as e:
            logger.debug("baostock_kline 获取失败 %s: %s", code, e)
            return None
