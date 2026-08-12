"""Baostock K 线数据源（需要 baostock 包）。

模块级一次性 login/logout，避免每次 fetch 都握手。
"""

import atexit
import logging
import threading
import time


from common import BaseFetcher, NOT_HANDLED, plain_code
from common.fetcher_base import _NotHandled
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

# P1-1: baostock IP 限流专项。
# baostock 匿名登录按 IP 限流，触发后封 IP（非账号），几小时到 24 小时恢复。
# 不同于 429（RateLimiter 处理），IP 封禁表现为连接超时/错误，需主动退避。
# 参考: https://zhuanlan.zhihu.com/p/2067944129309446823 第二节
_IP_BAN_FAILURE_THRESHOLD = 3  # 连续失败 N 次判定疑似 IP 封禁
_IP_BAN_BACKOFF_SECONDS = 60  # 主动退避秒数（避免持续冲击被封 IP）
_consecutive_failures = 0
_failure_lock = threading.Lock()


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

    def fetch(self, code: str, **kwargs) -> list | None | _NotHandled:
        scale = kwargs.get("scale", 240)
        datalen = kwargs.get("datalen", 30)

        if scale != 240:
            return None  # baostock 只支持日线

        # baostock 格式: sh.600989 / sz.000858
        plain = plain_code(code).zfill(6)
        # baostock 不覆盖北交所（BSE：43/83/87/88/92/920 开头），
        # 直接返回 NOT_HANDLED 交给 tencent/akshare 等源，避免发必失败请求污染熔断器。
        # 此判断在 HAS_BAOSTOCK 之前：不覆盖北交所是数据源能力问题，与包是否安装无关。
        if plain.startswith(("43", "83", "87", "88", "92", "920")):
            return NOT_HANDLED

        if not HAS_BAOSTOCK:
            return None

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
            if result:
                _record_success()
            return result if result else None
        except (NetworkError, RateLimitError, HTTPStatusError, ParseError):
            _record_failure()
            raise  # 网络/限速/解析异常向上抛，触发熔断和退避
        except Exception as e:
            _record_failure()
            logger.debug("baostock_kline 获取失败 %s: %s", code, e)
            return None


def _record_failure() -> None:
    """P1-1: 记录 baostock 连续失败，达阈值时主动退避并提示 IP 封禁风险。

    baostock IP 封禁后旧 IP 几小时才恢复，持续请求只会加重封禁。
    达 _IP_BAN_FAILURE_THRESHOLD 次后 sleep _IP_BAN_BACKOFF_SECONDS，
    避免在 IP 封禁窗口内高频重试。
    """
    global _consecutive_failures
    with _failure_lock:
        _consecutive_failures += 1
        count = _consecutive_failures
    if count >= _IP_BAN_FAILURE_THRESHOLD:
        logger.warning(
            "baostock 连续失败 %d 次，疑似 IP 封禁，主动退避 %ds "
            "（换网络/热点可立即解封，旧 IP 几小时恢复）",
            count,
            _IP_BAN_BACKOFF_SECONDS,
        )
        time.sleep(_IP_BAN_BACKOFF_SECONDS)


def _record_success() -> None:
    """P1-1: 成功时重置连续失败计数。"""
    global _consecutive_failures
    with _failure_lock:
        _consecutive_failures = 0


def get_baostock_ip_risk() -> dict:
    """P1-1: 供 health.py 调用，返回 baostock IP 封禁风险状态。"""
    with _failure_lock:
        count = _consecutive_failures
    return {
        "consecutive_failures": count,
        "ip_ban_suspected": count >= _IP_BAN_FAILURE_THRESHOLD,
        "threshold": _IP_BAN_FAILURE_THRESHOLD,
    }
