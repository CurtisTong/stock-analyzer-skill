"""(#10) 业绩预告数据源（东方财富 RPT_LICO_FN_CPD）。

提供业绩预告类型（预增/预减/预亏/续盈/续亏/扭亏）和预告利润上下限，
供事件因子评估"财报雷"风险与超预期机会。
"""

import json
import logging
from datetime import datetime

from common import BaseFetcher, http_get, to_float, strip_prefix

logger = logging.getLogger(__name__)

# 业绩预告 API（东财数据中心）
# RPT_LICO_FN_CPD: 业绩预告明细
FORECAST_URL = (
    "https://datacenter-web.eastmoney.com/api/data/v1/get"
    "?sortColumns=NOTICE_DATE&sortTypes=-1&pageSize=10&pageNumber=1"
    "&reportName=RPT_LICO_FN_CPD"
    "&columns=SECURITY_CODE,SECURITY_NAME_ABBR,NOTICE_DATE,REPORT_DATE,"
    "FORECAST_TYPE,PROFIT_MIN,PROFIT_MAX,CHANGE_MIN,CHANGE_MAX,PRE_PROFIT"
    "&filter=(SECURITY_CODE='{code}')"
)

# 预告类型映射（东财编码 -> 中文）
FORECAST_TYPE_MAP = {
    "预增": "increase",
    "预减": "decrease",
    "预亏": "loss",
    "预盈": "profit",
    "续盈": "continue_profit",
    "续亏": "continue_loss",
    "扭亏": "turn_profit",
}


class PerformanceForecastFetcher(BaseFetcher):
    """业绩预告数据源 (#10)。"""

    def __init__(self):
        super().__init__("performance_forecast", priority=5)

    def fetch(self, code: str = "", **kwargs) -> dict | None:
        """获取个股业绩预告数据。

        Args:
            code: 股票代码（如 sh600519 或 600519）

        Returns:
            {"type": "forecast", "items": [...]} 或 None
        """
        if not code:
            return None

        # 标准化代码（去前缀，东财用纯数字）
        pure_code = strip_prefix(code)

        url = FORECAST_URL.format(code=pure_code)
        try:
            raw = http_get(url, timeout=self.timeout, max_retries=self.retry)
            data = json.loads(raw)
        except (json.JSONDecodeError, Exception) as e:
            logger.debug("业绩预告 JSON 解析失败 %s: %s", code, e)
            return None

        if not data or "result" not in data or not data["result"].get("data"):
            return None

        items = []
        for row in data["result"]["data"]:
            forecast_type_raw = row.get("FORECAST_TYPE", "")
            forecast_type = FORECAST_TYPE_MAP.get(forecast_type_raw, forecast_type_raw)

            items.append({
                "code": code,
                "name": row.get("SECURITY_NAME_ABBR", ""),
                "notice_date": row.get("NOTICE_DATE", ""),
                "report_date": row.get("REPORT_DATE", ""),
                "forecast_type": forecast_type,
                "forecast_type_raw": forecast_type_raw,
                "profit_min": to_float(row.get("PROFIT_MIN")),
                "profit_max": to_float(row.get("PROFIT_MAX")),
                "change_min": to_float(row.get("CHANGE_MIN")),
                "change_max": to_float(row.get("CHANGE_MAX")),
                "pre_profit": to_float(row.get("PRE_PROFIT")),
            })

        if not items:
            return None

        return {"type": "forecast", "items": items}
