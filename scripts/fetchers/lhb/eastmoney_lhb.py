"""东方财富龙虎榜数据源。"""

import json
import re

from common import BaseFetcher, http_get, to_float, strip_prefix

# 龙虎榜个股明细 API
LHB_DETAIL_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get?sortColumns=SECURITY_CODE&sortTypes=1&pageSize=50&pageNumber=1&reportName=RPT_DAILYBILLBOARD_DETAILSNEW&columns=ALL&filter=(TRADE_DATE>='{start_date}')(TRADE_DATE<='{end_date}')"

# 龙虎榜买卖席位 API
LHB_SEAT_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get?sortColumns=BUY_AMT&sortTypes=-1&pageSize=20&pageNumber=1&reportName=RPT_BILLBOARD_DAILYDETAILSBUY&columns=ALL&filter=(TRADE_DATE='{date}')(SECURITY_CODE='{code}')"


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

        url = LHB_DETAIL_URL.format(start_date=start_date, end_date=end_date)
        raw = http_get(url)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None

        if not data or data.get("success") is not True:
            return None

        result_data = data.get("result", {}).get("data", [])
        if not result_data:
            return None

        items = []
        for r in result_data:
            item = {
                "code": r.get("SECURITY_CODE", ""),
                "name": r.get("SECURITY_NAME_ABBR", ""),
                "date": r.get("TRADE_DATE", "")[:10],
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

        return {"type": "lhb_detail", "items": items}


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

        # 获取买入席位
        buy_url = LHB_SEAT_URL.format(date=date, code=plain)
        raw = http_get(buy_url)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None

        if not data or data.get("success") is not True:
            return None

        result_data = data.get("result", {}).get("data", [])
        if not result_data:
            return None

        buy_seats = []
        for r in result_data:
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
            f"sortColumns=SELL_AMT&sortTypes=-1&pageSize=20&pageNumber=1"
            f"&reportName=RPT_BILLBOARD_DAILYDETAILSSELL&columns=ALL"
            f"&filter=(TRADE_DATE='{date}')(SECURITY_CODE='{plain}')"
        )
        raw = http_get(sell_url)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {
                "type": "lhb_seat",
                "code": plain,
                "date": date,
                "buy_seats": buy_seats,
                "sell_seats": [],
            }

        sell_seats = []
        if data and data.get("success") is True:
            for r in data.get("result", {}).get("data", []):
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
        }


__all__ = ["LhbDetailFetcher", "LhbSeatFetcher"]
