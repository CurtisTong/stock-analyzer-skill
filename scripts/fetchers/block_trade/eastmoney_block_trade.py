"""东方财富大宗交易数据源。

接口：datacenter-web.eastmoney.com RPT_DATA_BLOCKTRADE 报表。
字段单位（2026-10 实测）：DEAL_VOLUME 为股、DEAL_AMT 为元、
PREMIUM_RATIO 为小数比率（-0.0182 = 溢价率 -1.82%）。
"""

import json

from common import BaseFetcher, http_get, to_float, strip_prefix
from common.exceptions import (
    NetworkError,
    RateLimitError,
    HTTPStatusError,
    ParseError,
)
from fetchers.lhb.eastmoney_lhb import _fetch_all_pages

MAX_PAGES = 10

# 大宗交易明细（pageNumber 由分页循环注入）
BLOCK_TRADE_URL = (
    "https://datacenter-web.eastmoney.com/api/data/v1/get"
    "?sortColumns=TRADE_DATE&sortTypes=-1&pageSize=50&pageNumber={page}"
    "&reportName=RPT_DATA_BLOCKTRADE&columns=ALL"
    "&filter=(TRADE_DATE>='{start_date}')(TRADE_DATE<='{end_date}'){code_filter}"
)


class BlockTradeFetcher(BaseFetcher):
    """大宗交易明细数据源。"""

    def __init__(self):
        super().__init__("block_trade", priority=5)

    def fetch(self, code: str = "", **kwargs) -> dict | None:
        """获取大宗交易记录。code 为空时返回全市场近期记录。

        Args:
            code: 股票代码（sh600519），空 = 全市场
            days: 回看自然日窗口（默认 7）
        """
        from datetime import timedelta

        from dev.clock import now

        days = kwargs.get("days", 7)
        end_date = now().strftime("%Y-%m-%d")
        start_date = (now() - timedelta(days=days)).strftime("%Y-%m-%d")

        code_filter = f"(SECURITY_CODE='{strip_prefix(code)}')" if code else ""
        url = BLOCK_TRADE_URL.format(start_date=start_date, end_date=end_date, code_filter=code_filter, page="{page}")
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
            # client 侧过滤兜底：与服务端 code_filter 双保险（与 lhb_detail 一致）
            if code and r.get("SECURITY_CODE", "") != strip_prefix(code):
                continue
            trade_date = (r.get("TRADE_DATE") or "")[:10]
            premium = r.get("PREMIUM_RATIO")
            items.append(
                {
                    "code": r.get("SECURITY_CODE", ""),
                    "name": r.get("SECURITY_NAME_ABBR", ""),
                    "date": trade_date,
                    "deal_price": to_float(r.get("DEAL_PRICE", 0)),
                    "close": to_float(r.get("CLOSE_PRICE", 0)),
                    "change_pct": to_float(r.get("CHANGE_RATE", 0)),
                    # 成交量单位为股，换算为万股便于展示
                    "deal_volume_wan": round(to_float(r.get("DEAL_VOLUME", 0)) / 1e4, 2),
                    "deal_amt": to_float(r.get("DEAL_AMT", 0)),
                    # 小数比率 → 百分数（缺失为 None，不伪装成 0 溢价）
                    "premium_ratio": round(premium * 100, 2) if premium is not None else None,
                    "buyer": r.get("BUYER_NAME", ""),
                    "seller": r.get("SELLER_NAME", ""),
                }
            )

        return {"type": "block_trade", "items": items, "truncated": truncated}


__all__ = ["BlockTradeFetcher"]
