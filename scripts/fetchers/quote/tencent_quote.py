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


class TencentQuoteFetcher(BaseFetcher):
    """腾讯行情数据源 (优先级 10)。"""

    def __init__(self):
        super().__init__("tencent_quote", priority=10)

    def fetch(self, code: str, **kwargs) -> dict | None:
        url = TENCENT_URL.format(codes=code)
        raw = http_get(url, timeout=self.timeout, max_retries=self.retry)
        text = decode_gbk(raw)
        for line in text.strip().split(";"):
            line = line.strip()
            if not line:
                continue
            rec = parse_tencent_line(line)
            if rec:
                # P1-01: 校验返回的 code 与请求 code 一致，避免多行响应时返回错误记录
                if plain_code(rec["code"]) != plain_code(code):
                    logger.debug(
                        "腾讯行情 code 不匹配，跳过: 请求=%s 返回=%s", code, rec["code"]
                    )
                    continue
                rec["source"] = "tencent"
                # volume/amount 归一化在 data 层 _dict_to_quote 统一进行，
                # 此处保留原始单位（手/万元），避免双重归一化。
                return rec
        logger.debug("腾讯行情无数据: %s", code)
        return None
