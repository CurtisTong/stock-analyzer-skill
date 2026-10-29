"""可转债行情数据源（东财 push2 转债板块 b:MK0354）。

字段（2026-10 实测）：f2 最新价、f3 涨跌幅、f12 代码、f14 名称、
f127 转股溢价率%（双低值 = 价格 + 溢价率×100，越低性价比越高）。
"""

import json

from common import BaseFetcher, http_get_with_headers, to_float, strip_prefix
from common.exceptions import (
    NetworkError,
    RateLimitError,
    HTTPStatusError,
    ParseError,
)

MAX_PAGES = 5

CB_LIST_URL = (
    "https://push2.eastmoney.com/api/qt/clist/get"
    "?pn={page}&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3&fs=b:MK0354"
    "&fields=f2,f3,f12,f14,f127"
)


class ConvertibleBondFetcher(BaseFetcher):
    """可转债行情数据源（全市场转债列表，含价格/溢价率/双低值）。"""

    def __init__(self):
        super().__init__("cb_quote", priority=5)

    def fetch(self, code: str = "", **kwargs) -> dict | None:
        """获取可转债行情列表。

        Args:
            code: 转债代码（如 123291）；空 = 全市场
            top: 返回条数上限（默认 50，按溢价率升序 = 性价比优先）
        """
        top = kwargs.get("top", 50)

        all_records = []
        truncated = False
        page = 1
        total_pages = 1
        while page <= total_pages and page <= MAX_PAGES:
            url = CB_LIST_URL.format(page=page)
            try:
                raw = http_get_with_headers(
                    url,
                    headers={"Referer": "https://quote.eastmoney.com/"},
                    timeout=self.timeout,
                    max_retries=self.retry,
                )
            except (NetworkError, RateLimitError, HTTPStatusError, ParseError):
                raise
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                break
            if not isinstance(data, dict) or data.get("rc", 0) != 0:
                break
            result = data.get("data") or {}
            if page == 1:
                total = result.get("total", 0) or 0
                total_pages = max(1, -(-total // 100))
            diff = result.get("diff") or []
            if not diff:
                break
            all_records.extend(diff)
            page += 1
        truncated = page - 1 > MAX_PAGES

        if not all_records:
            return None

        items = []
        for r in all_records:
            if code and str(r.get("f12", "")) != strip_prefix(code):
                continue
            price = to_float(r.get("f2", 0))
            if price <= 0:
                continue  # 未上市/已摘牌无行情
            premium = r.get("f127")
            premium_f = to_float(premium) if premium not in (None, "-", "") else None
            items.append(
                {
                    "code": str(r.get("f12", "")),
                    "name": r.get("f14", ""),
                    "price": price,
                    "change_pct": to_float(r.get("f3", 0)),
                    # 转股溢价率%（f127 返回百分数数值，如 -6.81 = -6.81%；缺失为 None）
                    "premium_ratio": premium_f,
                    # 双低值 = 价格 + 转股溢价率数值（集思录口径：低 = 高性价比）
                    "double_low": round(price + (premium_f or 0), 2) if premium_f is not None else None,
                }
            )
        if code and not items:
            return None

        # 按双低值升序（性价比优先），缺失双低的排末尾
        items.sort(key=lambda i: (i["double_low"] is None, i["double_low"] or 9999))
        return {"type": "cb_quote", "items": items[:top], "total": len(items), "truncated": truncated}


__all__ = ["ConvertibleBondFetcher"]
