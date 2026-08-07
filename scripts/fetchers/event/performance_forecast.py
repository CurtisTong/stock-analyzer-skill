"""(#10) 业绩预告数据源（东方财富 RPT_PUBLIC_OP_PREDICT）。

提供业绩预告类型（预增/预减/预亏/续盈/续亏/扭亏）、预告利润上下限、
变动幅度上下限及文字说明，供事件因子评估"财报雷"风险与超预期机会。

注意：
- reportName 必须是 RPT_PUBLIC_OP_PREDICT（业绩预告），非 RPT_LICO_FN_CPD（财务摘要）。
- filter 中 SECURITY_CODE 值不加引号，加引号会触发 antlr InputMismatchException。
- 字段名与东财实际返回一致：FORECASTTYPE / FORECASTL / FORECASTT / INCREASEL /
  INCREASET / YEAREARLIER / FORECASTCONTENT 等（非早期猜测的 FORECAST_TYPE / PROFIT_MIN）。
"""

import json
import logging

from common import BaseFetcher, http_get, to_float, strip_prefix

logger = logging.getLogger(__name__)

# 单次抓取最大页数（防失控，pageSize=10，理论上限 200 条记录）
MAX_PAGES = 20

# 业绩预告 API（东财数据中心）
# RPT_PUBLIC_OP_PREDICT: 业绩预告明细（pageNumber 由分页循环注入）
# ⚠️ filter 中 SECURITY_CODE 不加引号（加引号触发 InputMismatchException）
FORECAST_URL = (
    "https://datacenter-web.eastmoney.com/api/data/v1/get"
    "?sortColumns=NOTICE_DATE&sortTypes=-1&pageSize=10&pageNumber={page}"
    "&reportName=RPT_PUBLIC_OP_PREDICT"
    "&columns=SECURITY_CODE,SECURITY_NAME_ABBR,NOTICE_DATE,REPORTDATE,"
    "FORECASTTYPE,FORECASTL,FORECASTT,INCREASEL,INCREASET,INCREASEJZ,"
    "FORECASTJZ,FORECASTQK,YEAREARLIER,FORECASTCONTENT,CHANGEREASONDSCRPT,ISLATEST"
    "&filter=(SECURITY_CODE={code})"
)


def _fetch_all_pages(build_url, timeout: int, retry: int):
    """分页抓取东财 datacenter API，累积所有页的 result.data。

    Args:
        build_url: 接收页码 page(int)、返回完整请求 URL 的回调。
        timeout / retry: 透传给 http_get。

    Returns:
        (all_records, truncated): all_records 为累积的原始记录列表；
        truncated 表示实际总页数超过 MAX_PAGES 而被截断。

    Note:
        网络/解析等任意异常向上抛出（由调用方统一捕获并降级）；
        仅 json.JSONDecodeError 会中断循环并保留已累积记录。
    """
    all_records = []
    page = 1
    total_pages = 1
    while page <= total_pages and page <= MAX_PAGES:
        raw = http_get(build_url(page), timeout=timeout, max_retries=retry)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            break
        if not data or "result" not in data:
            break
        result = data["result"] or {}
        if page == 1:
            # eastmoney datacenter 返回 result.pages；缺失时默认只取第一页
            total_pages = result.get("pages", 1) or 1
        records = result.get("data", []) or []
        if not records:
            break
        all_records.extend(records)
        page += 1
    return all_records, total_pages > MAX_PAGES


# 预告类型映射（东财 FORECASTTYPE 值 -> 英文枚举）
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

        url = FORECAST_URL.format(code=pure_code, page="{page}")
        try:
            result_data, truncated = _fetch_all_pages(
                lambda p: url.format(page=p),
                timeout=self.timeout,
                retry=self.retry,
            )
        except Exception as e:
            logger.debug("业绩预告获取失败 %s: %s", code, e)
            return None

        if not result_data:
            return None

        items = []
        for row in result_data:
            forecast_type_raw = row.get("FORECASTTYPE", "") or ""
            forecast_type = FORECAST_TYPE_MAP.get(forecast_type_raw, forecast_type_raw)
            # FORECASTQK 是东财预提供的英文枚举，缺失时回退到本地映射
            if not forecast_type:
                forecast_type = row.get("FORECASTQK", "") or ""

            items.append(
                {
                    "code": code,
                    "name": row.get("SECURITY_NAME_ABBR", ""),
                    "notice_date": str(row.get("NOTICE_DATE", ""))[:10],
                    "report_date": str(row.get("REPORTDATE", ""))[:10],
                    "forecast_type": forecast_type,
                    "forecast_type_raw": forecast_type_raw,
                    # 预告利润上下限（元）
                    "profit_min": to_float(row.get("FORECASTL")),
                    "profit_max": to_float(row.get("FORECASTT")),
                    # 变动幅度上下限（%）
                    "change_min": to_float(row.get("INCREASEL")),
                    "change_max": to_float(row.get("INCREASET")),
                    "change_midpoint": to_float(row.get("INCREASEJZ")),
                    "forecast_midpoint": to_float(row.get("FORECASTJZ")),
                    # 上年同期利润（元）
                    "pre_profit": to_float(row.get("YEAREARLIER")),
                    # 文字说明
                    "content": row.get("FORECASTCONTENT", "") or "",
                    "reason": row.get("CHANGEREASONDSCRPT", "") or "",
                    "is_latest": row.get("ISLATEST", "") == "T",
                }
            )

        if not items:
            return None

        return {"type": "forecast", "items": items, "truncated": truncated}
