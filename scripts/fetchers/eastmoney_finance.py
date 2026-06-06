"""东方财富财务数据源。"""
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import BaseFetcher, http_get

URL = "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/ZYZBAjaxNew?type=0&code={code}"


class EastmoneyFinanceFetcher(BaseFetcher):
    """东方财富财务数据源 (优先级 10)。缓存由 data 层统一管理。"""

    def __init__(self):
        super().__init__("eastmoney_finance", priority=10)

    def fetch(self, code: str, **kwargs) -> list | None:
        raw = http_get(URL.format(code=code))
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not data or "data" not in data or not data["data"]:
            return None
        result = data["data"][:4]
        for r in result:
            r["source"] = "eastmoney"
        return result
