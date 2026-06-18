"""腾讯行情数据源。"""
from pathlib import Path

from common import BaseFetcher, http_get, decode_gbk, parse_tencent_line, normalize_volume, normalize_amount

TENCENT_URL = "https://qt.gtimg.cn/q={codes}"


class TencentQuoteFetcher(BaseFetcher):
    """腾讯行情数据源 (优先级 10)。"""

    def __init__(self):
        super().__init__("tencent_quote", priority=10)

    def fetch(self, code: str, **kwargs) -> dict | None:
        url = TENCENT_URL.format(codes=code)
        raw = http_get(url)
        text = decode_gbk(raw)
        for line in text.strip().split(";"):
            line = line.strip()
            if not line:
                continue
            rec = parse_tencent_line(line)
            if rec:
                rec["source"] = "tencent"
                rec["volume"] = normalize_volume(rec["volume"], "tencent")
                rec["amount"] = normalize_amount(rec["amount"], "tencent")
                return rec
        return None
