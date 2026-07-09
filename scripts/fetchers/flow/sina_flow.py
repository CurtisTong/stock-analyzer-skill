"""新浪资金流向数据源（北向资金备份）。

新浪财经提供北向资金历史数据，作为 eastmoney 的备份源。
"""

import json

from common import BaseFetcher, http_get, to_float

# 新浪财经北向资金 API（fltt=2 表示前复权，lmt 控制天数）
SINA_NORTHBOUND_URL = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "CN_MarketData.getKLineData?symbol=hsgt&scale=240&datalen={days}"
)


class SinaNorthboundFlowFetcher(BaseFetcher):
    """新浪北向资金 fetcher（备份源）。"""

    def __init__(self):
        super().__init__("northbound_flow", priority=8)  # 较低优先级（备份）

    def fetch(self, code: str = "", **kwargs) -> dict | None:
        days = kwargs.get("days", 10)
        url = SINA_NORTHBOUND_URL.format(days=days)
        try:
            raw = http_get(url, timeout=self.timeout, max_retries=self.retry)
        except Exception:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not data or not isinstance(data, list):
            return None

        result = {"type": "northbound", "days": [], "source": "sina"}
        for row in data:
            if not isinstance(row, dict):
                continue
            # 新浪字段：day/open/close/high/low/volume
            # 北向资金的 close 等字段含义：当日净流入额（亿元）
            # 归一化：与东财（万元）对齐 → 乘以 10000
            date = row.get("day", "")
            close_yi = to_float(row.get("close"))  # 当日净流入（亿元）
            close_wan = close_yi * 10000  # → 万元
            result["days"].append({
                "date": date,
                "total_net": close_wan,
                "sh_net": 0,  # 新浪不区分沪/深
                "sz_net": 0,
                "_source_breakdown_unavailable": True,
            })
        return result if result["days"] else None
