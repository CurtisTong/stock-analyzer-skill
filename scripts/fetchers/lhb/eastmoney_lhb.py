"""东方财富龙虎榜数据源。"""

import json

from common import BaseFetcher, http_get, to_float, strip_prefix
from common.exceptions import (
    NetworkError,
    RateLimitError,
    HTTPStatusError,
    ParseError,
)

# 单次抓取最大页数（防失控，pageSize=50/20，理论上限 1000/400 条记录）
MAX_PAGES = 20

# 龙虎榜个股明细 API（pageNumber 由分页循环注入）
LHB_DETAIL_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get?sortColumns=SECURITY_CODE&sortTypes=1&pageSize=50&pageNumber={page}&reportName=RPT_DAILYBILLBOARD_DETAILSNEW&columns=ALL&filter=(TRADE_DATE>='{start_date}')(TRADE_DATE<='{end_date}')"

# 龙虎榜买卖席位 API（pageNumber 由分页循环注入）
LHB_SEAT_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get?sortColumns=BUY_AMT&sortTypes=-1&pageSize=20&pageNumber={page}&reportName=RPT_BILLBOARD_DAILYDETAILSBUY&columns=ALL&filter=(TRADE_DATE='{date}')(SECURITY_CODE='{code}')"


def _fetch_all_pages(build_url, timeout: int, retry: int):
    """分页抓取东财 datacenter API，累积所有页的 result.data。

    Args:
        build_url: 接收页码 page(int)、返回完整请求 URL 的回调。
        timeout / retry: 透传给 http_get。

    Returns:
        (all_records, truncated): all_records 为累积的原始记录列表；
        truncated 表示实际总页数超过 MAX_PAGES 而被截断。

    Note:
        网络/限速/HTTP 异常向上抛出（触发熔断），与单页实现保持一致；
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
        if not data or data.get("success") is not True:
            break
        result = data.get("result", {}) or {}
        if page == 1:
            # eastmoney datacenter 返回 result.pages；缺失时默认只取第一页
            total_pages = result.get("pages", 1) or 1
        records = result.get("data", []) or []
        if not records:
            break
        all_records.extend(records)
        page += 1
    return all_records, total_pages > MAX_PAGES


class LhbDetailFetcher(BaseFetcher):
    """龙虎榜明细数据源。"""

    def __init__(self):
        super().__init__("lhb_detail", priority=5)

    def fetch(self, code: str = "", **kwargs) -> dict | None:
        """获取龙虎榜数据。code 为空时返回近期全部龙虎榜。"""
        from datetime import timedelta

        from dev.clock import now

        days = kwargs.get("days", 7)
        end_date = now().strftime("%Y-%m-%d")
        start_date = (now() - timedelta(days=days)).strftime("%Y-%m-%d")

        url = LHB_DETAIL_URL.format(
            start_date=start_date, end_date=end_date, page="{page}"
        )
        try:
            result_data, truncated = _fetch_all_pages(
                lambda p: url.format(page=p),
                timeout=self.timeout,
                retry=self.retry,
            )
        except (NetworkError, RateLimitError, HTTPStatusError, ParseError):
            raise
        if not result_data:
            return None

        items = []
        for r in result_data:
            item = {
                "code": r.get("SECURITY_CODE", ""),
                "name": r.get("SECURITY_NAME_ABBR", ""),
                "date": (r.get("TRADE_DATE") or "")[:10],
                "close": to_float(r.get("CLOSE_PRICE", 0)),
                "change_pct": to_float(r.get("CHANGE_RATE", 0)),
                "turnover_rate": to_float(r.get("TURNOVERRATE", 0)),
                "net_buy": to_float(r.get("NET_BUY_AMT", 0)),  # 龙虎榜净买入
                "buy_total": to_float(r.get("BUY_AMT", 0)),  # 买入总额
                "sell_total": to_float(r.get("SELL_AMT", 0)),  # 卖出总额
                "reason": r.get("EXPLANATION", ""),  # 上榜原因
            }
            # 如果指定了 code，只返回该股票的记录
            if code and item["code"] != strip_prefix(code):
                continue
            items.append(item)

        return {"type": "lhb_detail", "items": items, "truncated": truncated}


class LhbSeatFetcher(BaseFetcher):
    """龙虎榜买卖席位数据源。"""

    def __init__(self):
        super().__init__("lhb_seat", priority=5)

    def fetch(self, code: str, **kwargs) -> dict | None:
        """获取指定股票的龙虎榜买卖席位。"""
        from dev.clock import now

        date = kwargs.get("date", "")
        if not date:
            date = now().strftime("%Y-%m-%d")

        plain = strip_prefix(code)

        # 获取买入席位（分页累积）
        buy_url = LHB_SEAT_URL.format(date=date, code=plain, page="{page}")
        try:
            buy_records, buy_truncated = _fetch_all_pages(
                lambda p: buy_url.format(page=p),
                timeout=self.timeout,
                retry=self.retry,
            )
        except (NetworkError, RateLimitError, HTTPStatusError, ParseError):
            raise
        if not buy_records:
            return None

        buy_seats = []
        for r in buy_records:
            buy_seats.append(
                {
                    "name": r.get("BUYER_NAME", ""),
                    "buy_amt": to_float(r.get("BUY_AMT", 0)),
                    "buy_pct": to_float(r.get("BUY_AMT_RATIO", 0)),
                    "sell_amt": to_float(r.get("SELL_AMT", 0)),
                    "reason": r.get("EXPLANATION", ""),
                }
            )

        # 获取卖出席位（显式构造参数，避免字符串替换带来的隐式依赖）
        sell_url = (
            f"https://datacenter-web.eastmoney.com/api/data/v1/get?"
            f"sortColumns=SELL_AMT&sortTypes=-1&pageSize=20&pageNumber={{page}}"
            f"&reportName=RPT_BILLBOARD_DAILYDETAILSSELL&columns=ALL"
            f"&filter=(TRADE_DATE='{date}')(SECURITY_CODE='{plain}')"
        )
        try:
            sell_records, sell_truncated = _fetch_all_pages(
                lambda p: sell_url.format(page=p),
                timeout=self.timeout,
                retry=self.retry,
            )
        except (NetworkError, RateLimitError, HTTPStatusError, ParseError):
            raise

        sell_seats = []
        for r in sell_records:
            sell_seats.append(
                {
                    "name": r.get("SELLER_NAME", ""),
                    "sell_amt": to_float(r.get("SELL_AMT", 0)),
                    "sell_pct": to_float(r.get("SELL_AMT_RATIO", 0)),
                    "buy_amt": to_float(r.get("BUY_AMT", 0)),
                }
            )

        return {
            "type": "lhb_seat",
            "code": plain,
            "date": date,
            "buy_seats": buy_seats,
            "sell_seats": sell_seats,
            "truncated": buy_truncated or sell_truncated,
        }


__all__ = ["LhbDetailFetcher", "LhbSeatFetcher"]
