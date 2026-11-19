"""腾讯行情数据源。"""

import logging

from common import (
    BaseFetcher,
    http_get,
    decode_gbk,
    parse_tencent_line,
    plain_code,
)

logger = logging.getLogger(__name__)

TENCENT_URL = "https://qt.gtimg.cn/q={codes}"

# 美股指数：腾讯用 usDJI/usIXIC/usINX 三个符号，标准符号（^GSPC 等）需先映射。
# 这里有源可用，此前 us: 前缀只走 yfinance/雪球，两源 429/400 时整段失效。
_US_INDEX_SYMBOLS = {
    "us:^gspc": "usINX",
    "us:^spx": "usINX",
    "us:^inx": "usINX",
    "us:^ixic": "usIXIC",
    "us:^ndq": "usIXIC",
    "us:^dji": "usDJI",
    "us:^djia": "usDJI",
}


class TencentQuoteFetcher(BaseFetcher):
    """腾讯行情数据源 (优先级 10)。"""

    def __init__(self):
        super().__init__("tencent_quote", priority=10)

    def fetch(self, code: str, **kwargs) -> dict | None:
        symbol = _US_INDEX_SYMBOLS.get(code.strip().lower())
        if symbol is not None:
            return self._fetch_us_index(code, symbol)

        url = TENCENT_URL.format(codes=code)
        raw = http_get(url, timeout=self.timeout, max_retries=self.retry)
        text = decode_gbk(raw)
        for line in text.strip().split(";"):
            line = line.strip()
            if not line:
                continue
            rec = parse_tencent_line(line)
            if rec:
                # 校验返回的 code 与请求 code 一致，避免多行响应时返回错误记录
                if plain_code(rec["code"]) != plain_code(code):
                    logger.debug("腾讯行情 code 不匹配，跳过: 请求=%s 返回=%s", code, rec["code"])
                    continue
                rec["source"] = "tencent"
                # volume/amount 归一化在 data 层 _dict_to_quote 统一进行，
                # 此处保留原始单位（手/万元），避免双重归一化。
                return rec
        logger.debug("腾讯行情无数据: %s", code)
        return None

    def _fetch_us_index(self, code: str, symbol: str) -> dict | None:
        """美股指数：按 usDJI/usIXIC/usINX 取数，返回时保留调用方传入的代码。"""
        url = TENCENT_URL.format(codes=symbol)
        raw = http_get(url, timeout=self.timeout, max_retries=self.retry)
        text = decode_gbk(raw)
        for line in text.strip().split(";"):
            line = line.strip()
            if not line:
                continue
            rec = parse_tencent_line(line)
            if rec and rec.get("name"):
                rec["code"] = code.lower()
                rec["source"] = "tencent"
                return rec
        logger.debug("腾讯美股指数无数据: %s (%s)", code, symbol)
        return None
