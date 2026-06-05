"""新浪行情数据源。"""
import sys
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import BaseFetcher, parse_sina_quote_line

SINA_URL = "https://hq.sinajs.cn/list={codes}"


class SinaQuoteFetcher(BaseFetcher):
    """新浪行情数据源 (优先级 5)。"""

    def __init__(self):
        super().__init__("sina_quote", priority=5)

    def fetch(self, code: str, **kwargs) -> dict | None:
        url = SINA_URL.format(codes=code)
        req = urllib.request.Request(url, headers={
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read()
        text = raw.decode("gbk", errors="replace")
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            rec = parse_sina_quote_line(line)
            if rec:
                return rec
        return None
