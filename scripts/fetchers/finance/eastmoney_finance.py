"""东方财富财务数据源。"""

import json
import logging

from common import BaseFetcher, http_get

logger = logging.getLogger(__name__)

URL = "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/ZYZBAjaxNew?type=0&code={code}"


class EastmoneyFinanceFetcher(BaseFetcher):
    """东方财富财务数据源 (优先级 10)。缓存由 data 层统一管理。"""

    def __init__(self):
        super().__init__("eastmoney_finance", priority=10)

    def fetch(self, code: str, **kwargs) -> list | None:
        # periods 控制返回期数（默认 4 保持向后兼容；full/debate 模式传 8）
        try:
            periods = int(kwargs.get("periods", 4))
        except (TypeError, ValueError):
            periods = 4
        periods = max(1, periods)

        raw = http_get(
            URL.format(code=code), timeout=self.timeout, max_retries=self.retry
        )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("东方财富财务 JSON 解析失败: %s", code)
            return None
        if not data or "data" not in data or not data["data"]:
            logger.debug("东方财富财务无数据: %s", code)
            return None
        result = data["data"][:periods]
        for r in result:
            r["source"] = "eastmoney"
        return result
