"""东方财富行情数据源。"""

import json
import logging

from common import BaseFetcher, http_get, to_float, to_secid
from common.exceptions import ParseError

logger = logging.getLogger(__name__)

EASTMONEY_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f60,f116,f117,f162,f167,f168,f169,f170"


def _div100(v):
    try:
        return str(round(float(v) / 100, 2))
    except (TypeError, ValueError):
        return None


class EastmoneyQuoteFetcher(BaseFetcher):
    """东方财富行情数据源 (优先级 8)。"""

    def __init__(self):
        super().__init__("eastmoney_quote", priority=8)

    def fetch(self, code: str, **kwargs) -> dict | None:
        secid = to_secid(code)
        url = EASTMONEY_QUOTE_URL.format(secid=secid)
        raw = http_get(url, timeout=self.timeout, max_retries=self.retry)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ParseError(raw, "eastmoney_quote", f"JSON 解析失败: {code} url={url}") from e
        if not data or data.get("rc") != 0 or "data" not in data:
            logger.debug("东方财富行情无数据: %s", code)
            return None
        d = data["data"]
        if not d:
            logger.debug("东方财富行情 data 为空: %s", code)
            return None

        # P1-8 (2026-11-21 review §3.1 #8)：核心字段为 "-" / None / 0 时，
        # _div100 返回 None，to_float(None)=0 会把“无报价”伪装成 0 价成功响应，
        # 错误源不熔断、不切源。这里先校验 price，无效则返回 None（manager 切源）。
        price = _div100(d.get("f43"))
        if price is None or to_float(price, 0.0) <= 0:
            logger.warning(
                "东方财富行情核心字段 price 无效(%r)，放弃该源让 manager 切源: %s",
                d.get("f43"),
                code,
            )
            return None

        code_str = str(d.get("f57", ""))
        if code_str and len(code_str) < 6:
            code_str = code_str.zfill(6)

        return {
            "code": code_str,
            "name": d.get("f58", ""),
            "price": price,
            "prev_close": _div100(d.get("f60", 0)),
            "open": _div100(d.get("f46", 0)),
            "change_pct": _div100(d.get("f170", 0)),
            "change_amt": _div100(d.get("f169", 0)),
            "high": _div100(d.get("f44", 0)),
            "low": _div100(d.get("f45", 0)),
            "volume": d.get("f47", 0),
            "amount": d.get("f48", 0),
            "turnover": _div100(d.get("f168", 0)),
            "pe": _div100(d.get("f162", 0)),
            "pe_type": "dynamic",  # f162 为动态市盈率
            "pb": _div100(d.get("f167", 0)),
            "total_cap": str(d.get("f116", 0)),  # 原始元值，归一化在 data 层 _normalize_cap
            "circulating_cap": str(d.get("f117", 0)),
            "source": "eastmoney",
        }
