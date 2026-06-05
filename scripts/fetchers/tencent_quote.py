"""腾讯行情数据源。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import BaseFetcher, http_get, decode_gbk, parse_tencent_line

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
                return rec
        return None
