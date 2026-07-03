"""Tushare 行情数据源（需要 tushare 包 + token）。"""

import logging
import os

from common import BaseFetcher

logger = logging.getLogger(__name__)


def _check_tushare() -> bool:
    """运行时检查 tushare 是否可用（包已安装 + token 已设置）。"""
    if not os.environ.get("TUSHARE_TOKEN"):
        return False
    try:
        import tushare  # noqa: F401

        return True
    except ImportError:
        return False


class TushareQuoteFetcher(BaseFetcher):
    """Tushare 行情数据源 (优先级 -1) - 需要安装 tushare 包并设置 TUSHARE_TOKEN。"""

    def __init__(self):
        super().__init__("tushare_quote", priority=-1 if _check_tushare() else 2)

    def fetch(self, code: str, **kwargs) -> dict | None:
        if not _check_tushare():
            return None
        try:
            import tushare as ts

            token = os.environ.get("TUSHARE_TOKEN", "")
            if token:
                ts.set_token(token)

            plain = code.lstrip("shszSHSZbjBJ")
            # 转换为 tushare 格式: 600989.SH
            if code.startswith(("sh", "SH")):
                ts_code = f"{plain}.SH"
            else:
                ts_code = f"{plain}.SZ"

            pro = ts.pro_api()
            df = pro.daily(ts_code=ts_code, limit=1)
            if df is None or df.empty:
                return None
            r = df.iloc[0]
            return {
                "code": plain,
                "name": "",
                "price": str(r.get("close", 0)),
                "prev_close": str(r.get("pre_close", 0)),
                "open": str(r.get("open", 0)),
                "change_pct": str(r.get("pct_chg", 0)),
                "change_amt": str(r.get("change", 0)),
                "high": str(r.get("high", 0)),
                "low": str(r.get("low", 0)),
                "volume": str(r.get("vol", 0)),
                "amount": str(r.get("amount", 0)),
                "turnover": "",
                "pe": "",
                "pb": "",
                "total_cap": "",
                "circulating_cap": "",
                "source": "tushare",
            }
        except Exception as e:
            logger.debug("tushare_quote 获取失败 %s: %s", code, e)
            return None
