"""新浪行情数据源。"""

import logging

from common import (
    BaseFetcher,
    parse_sina_quote_line,
    http_get_with_headers,
    decode_gbk,
)

logger = logging.getLogger(__name__)

SINA_URL = "https://hq.sinajs.cn/list={codes}"


class SinaQuoteFetcher(BaseFetcher):
    """新浪行情数据源 (优先级 5)。"""

    def __init__(self):
        super().__init__("sina_quote", priority=5)

    def fetch(self, code: str, **kwargs) -> dict | None:
        url = SINA_URL.format(codes=code)
        raw = http_get_with_headers(
            url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=self.timeout
        )
        text = decode_gbk(raw)
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            rec = parse_sina_quote_line(line)
            if rec:
                rec["source"] = "sina"
                # volume/amount 归一化在 data 层 _dict_to_quote 统一进行。
                return rec
        logger.debug("新浪行情无数据: %s", code)
        return None
