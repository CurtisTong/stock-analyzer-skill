"""新股/新债日历数据源（东财 RPT_IPO_CALENDAR）。

事件类型 DATE_TYPE：申购 / 中签号 / 缴款日 / 上市 / 股权登记等。
同时覆盖沪深股票 IPO 与可转债（SECURITY_TYPE=0 股票 / 1 债券）。
"""

import json

from common import BaseFetcher, http_get, strip_prefix
from common.exceptions import (
    NetworkError,
    RateLimitError,
    HTTPStatusError,
    ParseError,
)

MAX_PAGES = 3

# 新股日历（TRADE_DATE 降序，pageNumber 由分页循环注入）
IPO_CALENDAR_URL = (
    "https://datacenter-web.eastmoney.com/api/data/v1/get"
    "?sortColumns=TRADE_DATE&sortTypes=-1&pageSize=50&pageNumber={page}"
    "&reportName=RPT_IPO_CALENDAR&columns=ALL"
    "&filter=(TRADE_DATE>='{start_date}')"
)


class IpoCalendarFetcher(BaseFetcher):
    """新股日历数据源（打新日历：申购/中签/缴款/上市）。"""

    def __init__(self):
        super().__init__("ipo_calendar", priority=5)

    def fetch(self, code: str = "", **kwargs) -> dict | None:
        """获取近期新股/新债日历事件。

        Args:
            code: 股票代码（可选，过滤）
            days: 未来回看窗口（自然日，默认取未来 30 天 + 过去 3 天）
        """
        from datetime import timedelta

        from dev.clock import now

        future_days = kwargs.get("days", 30)
        today = now().date()
        start_date = (today - timedelta(days=3)).strftime("%Y-%m-%d")
        end_date = (today + timedelta(days=future_days)).strftime("%Y-%m-%d")

        url = IPO_CALENDAR_URL.format(start_date=start_date, page="{page}")
        url += f"(TRADE_DATE<='{end_date}')"

        all_records = []
        truncated = False
        page = 1
        total_pages = 1
        while page <= total_pages and page <= MAX_PAGES:
            try:
                raw = http_get(url.format(page=page), timeout=self.timeout, max_retries=self.retry)
            except (NetworkError, RateLimitError, HTTPStatusError, ParseError):
                raise
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                break
            if not isinstance(data, dict) or data.get("success") is not True:
                break
            result = data.get("result", {}) or {}
            if page == 1:
                total_pages = result.get("pages", 1) or 1
            records = result.get("data", []) or []
            if not records:
                break
            all_records.extend(records)
            page += 1
        truncated = page - 1 > MAX_PAGES

        if not all_records:
            return None

        items = []
        for r in all_records:
            if code and r.get("SECURITY_CODE", "") != strip_prefix(code):
                continue
            items.append(
                {
                    "code": r.get("SECURITY_CODE", ""),
                    "name": r.get("SECURITY_NAME_ABBR", ""),
                    "date": (r.get("TRADE_DATE") or "")[:10],
                    "event_type": r.get("DATE_TYPE", ""),  # 申购/中签号/缴款日/上市
                    "security_type": "债券" if str(r.get("SECURITY_TYPE", "0")) == "1" else "股票",
                }
            )
        if code and not items:
            return None

        return {"type": "ipo_calendar", "items": items, "truncated": truncated}


__all__ = ["IpoCalendarFetcher"]
