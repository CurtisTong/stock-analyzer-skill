"""东方财富财务数据源。"""
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import BaseFetcher, http_get, cache_key_for_stock, cache_get, cache_set

URL = "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/ZYZBAjaxNew?type=0&code={code}"


class EastmoneyFinanceFetcher(BaseFetcher):
    """东方财富财务数据源 (优先级 10)。"""

    def __init__(self):
        super().__init__("eastmoney_finance", priority=10)

    def fetch(self, code: str, **kwargs) -> list | None:
        use_cache = kwargs.get("use_cache", True)
        key = cache_key_for_stock("finance", code)
        if use_cache:
            cached = cache_get(key, ttl_seconds=21600)
            if cached is not None:
                try:
                    return json.loads(cached)
                except json.JSONDecodeError:
                    pass

        raw = http_get(URL.format(code=code))
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not data or "data" not in data or not data["data"]:
            return None
        result = data["data"][:4]

        if use_cache and result:
            cache_set(key, json.dumps(result, ensure_ascii=False).encode())
        return result
